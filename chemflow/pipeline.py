"""
Orkestrator utama pipeline chemflow. Menjalankan seluruh tahap secara
berurutan: baca Excel -> resolusi SMILES -> preparasi ligan -> ADMET ->
preparasi reseptor -> docking (matriks + replikasi) -> ligan native (redocking,
Lipinski, ADMET) -> validasi RMSD -> merge kompleks -> ekspor hasil ->
analitik (chart, grafik per grup, heatmap, PCA, HCA).

Kegagalan pada satu ligan/reseptor tidak menghentikan seluruh run.
Dicatat sebagai warning/error dan dilaporkan di ringkasan akhir, sisanya
tetap diproses (filosofi yang sama dipakai konsisten di semua modul
chemflow: tahap kosmetik/individual boleh gagal, tahap yang benar-benar
fatal untuk 1 item saja menghentikan proses item itu saja).

Setiap item yang selesai (ligan, reseptor beserta gridbox-nya, satu run
Vina, hasil ADMET per SMILES) langsung ditulis sebagai checkpoint atomik,
sehingga ``Pipeline(config, resume=True)`` (``chemflow resume --output``)
melanjutkan dari tahap terakhir setelah terminal ditutup, Ctrl+C, atau
komputer mati. Lihat ``chemflow/state.py`` dan ``chemflow/checkpoints.py``.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from tqdm import tqdm

from chemflow.admet.admet_file import load_admet_rows
from chemflow.admet.admet_rules import CATEGORIES, category_scores
from chemflow.admet.admetlab_scraper import AdmetLabScraper
from chemflow.admet.dedup import describe_duplicates, fan_out, group_by_smiles
from chemflow.analytics.charts import ChartBuilder
from chemflow.analytics.group_charts import GroupChartBuilder
from chemflow.analytics.group_stats import (
    NATIVE_GROUP, NO_GROUP, add_delta_vs_native, group_label, summarize_docking_by_group,
    summarize_groups, with_group,
)
from chemflow.analytics.hca import HierarchicalClustering
from chemflow.analytics.heatmap import HeatmapBuilder
from chemflow.analytics.pca import ChemometricPCA
from chemflow.checkpoints import load_ligand_prep, load_receptor, save_ligand_prep, save_receptor
from chemflow.chem.descriptors import LipinskiCalculator
from chemflow.chem.ligand_preparer import LigandPreparer, LigandPrepResult
from chemflow.chem.mol_converter import OpenBabelConverter
from chemflow.chem.pubchem_client import PubChemResolver, prompt_manual_smiles
from chemflow.chem.receptor_preparer import ReceptorPreparer
from chemflow.config import PipelineConfig
from chemflow.docking.docking_matrix import (
    DockingOrchestrator, DockingRunResult, ReceptorDockingTarget, compute_replicate_stats,
)
from chemflow.docking.grid_box import GridBox
from chemflow.docking.merge import merge_complex
from chemflow.docking.rmsd_validation import RedockingValidator
from chemflow.docking.vina_manager import VinaReleaseManager
from chemflow.docking.vina_runner import VinaRunner, resolve_vina_executable
from chemflow.io.excel_ligands import LigandRecord, read_ligands
from chemflow.io.excel_receptors import read_receptors
from chemflow.io.ligand_template import native_smiles as derive_native_smiles
from chemflow.io.pdb_fetcher import NativeLigand, fetch_pdb, interactive_select_native_ligand
from chemflow.io.pdbqt_reader import read_pdbqt
from chemflow.io.result_exporter import export_results
from chemflow.state import RunState, read_json, write_json_atomic
from chemflow.utils.logging_setup import setup_logging
from chemflow.utils.name_sanitizer import sanitize_filename


_DEFAULT_NAME_LENGTH = 60
_MIN_NAME_LENGTH = 8
_WINDOWS_PATH_LIMIT = 259


def _file_name(record: LigandRecord) -> str:
    return record.safe_name or sanitize_filename(record.name)


def _name_length_budget(output_path_length: int) -> int:
    """Panjang maksimum nama file ligan agar path terpanjang tetap di bawah batas Windows (260 karakter).

    Path terpanjang adalah ``ligands/<nama>/<nama>_2d.png`` (17 + 2 x nama)
    atau ``complexes/<kunci>/<nama>_rep01_mode01_complex.pdb`` (53 + nama).
    """
    room = min((_WINDOWS_PATH_LIMIT - 17 - output_path_length) // 2, _WINDOWS_PATH_LIMIT - 53 - output_path_length)
    return max(_MIN_NAME_LENGTH, min(_DEFAULT_NAME_LENGTH, room))


def _json_value(value: Any) -> Any:
    """Nilai sel DataFrame yang aman untuk JSON: NaN menjadi None, tipe numpy menjadi tipe Python."""
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


@dataclass
class NativeEntry:
    """Ligan native kokristal yang diperlakukan sebagai ligan referensi: di-dock ulang dan ikut analitik."""
    name: str                            # nama aman, mis. NATIVE_N3_A1101
    label: str                           # label asli, mis. N3_A1101
    receptor_key: str
    smiles: str
    prep: LigandPrepResult
    lipinski: Optional[Dict[str, Any]] = None


class Pipeline:
    """Menjalankan seluruh alur chemflow dari konfigurasi yang sudah divalidasi."""

    def __init__(self, config: PipelineConfig, resume: bool = False) -> None:
        self.cfg = config
        self._resume = resume
        self.log = setup_logging(self.cfg.output_dir / "chemflow.log",
                                  level=getattr(logging, self.cfg.log_level, logging.INFO))
        self._state = RunState(self.cfg.output_dir)
        self._obabel = OpenBabelConverter(self.cfg.openbabel_path, logger=self.log)
        self._ligand_preparer = LigandPreparer(self._obabel, logger=self.log)
        self._receptor_preparer = ReceptorPreparer(
            kollman_fallback="zero" if self.cfg.kollman_fallback_zero else "gasteiger", logger=self.log,
        )
        self._vina_manager = VinaReleaseManager(cache_dir=self.cfg.cache_dir / "vina", logger=self.log)

        self.failed_ligands: List[str] = []
        self.failed_receptors: List[str] = []
        self.failed_interactions: List[str] = []
        self._input_records: List[LigandRecord] = []
        self._group_of: Dict[str, str] = {}
        self._lipinski_by_name: Dict[str, Dict[str, Any]] = {}
        self._admet_cache: Dict[str, Dict[str, Any]] = {}
        self._natives: List[NativeEntry] = []
        self._native_errors: Dict[str, str] = {}
        self._reused: Dict[str, int] = {}

    def run(self) -> int:
        """Jalankan seluruh pipeline. Return 0 sukses, 1 jika gagal total (fatal), 130 jika dihentikan pengguna."""
        try:
            self._begin()

            ligand_records = self._read_and_resolve_ligands()
            self._stage("preparasi ligan")
            ligand_results = self._prepare_ligands(ligand_records)
            lipinski_rows = self._compute_lipinski(ligand_results)
            self._stage("ADMET")
            admet_rows = self._run_admet(ligand_results) if self.cfg.run_admet else []

            vina_exe = resolve_vina_executable(self._vina_manager, version=self.cfg.vina_version,
                                                explicit_path=self.cfg.vina_executable)
            vina_runner = VinaRunner(vina_exe, logger=self.log)
            orchestrator = DockingOrchestrator(vina_runner, logger=self.log)

            self._stage("preparasi reseptor")
            targets, rmsd_context = self._prepare_receptors()
            ligand_pdbqt_map = {name: r.pdbqt_path for name, r in ligand_results.items()}

            self._stage("docking")
            docking_results = orchestrator.run_matrix(
                ligand_pdbqt_map, targets, self.cfg.docking_dir,
                n_replicates=self.cfg.n_replicates, exhaustiveness=self.cfg.exhaustiveness,
                num_modes=self.cfg.num_modes, energy_range=self.cfg.energy_range, base_seed=self.cfg.seed,
                show_progress=self.cfg.show_progress, resume=self._resume,
            )
            self._count_reused("run docking", docking_results)

            self._stage("ligan native")
            self._natives = self._prepare_natives(rmsd_context, targets)
            native_results = self._dock_natives(orchestrator, targets)
            native_lipinski, native_admet = self._native_properties()

            rmsd_rows = []
            if self.cfg.run_rmsd_validation and rmsd_context:
                rmsd_rows = self._run_rmsd_validation(rmsd_context, native_results)

            self._stage("merge kompleks")
            self._merge_native_reference(rmsd_context, targets)
            self._merge_poses(docking_results, targets)

            self._stage("ekspor dan analitik")
            report_results = docking_results + (native_results if self.cfg.include_native else [])
            lipinski_rows = lipinski_rows + native_lipinski
            admet_rows = admet_rows + native_admet
            group_of = dict(self._group_of)

            replicate_stats = add_delta_vs_native(compute_replicate_stats(report_results), group_of)
            docking_rows = with_group(self._docking_rows(report_results), group_of)
            ligand_summary_rows = self._ligand_summary_rows(ligand_records, ligand_results)

            export_path = self.cfg.output_dir / "hasil_chemflow.xlsx"
            export_results(
                export_path, ligand_summary_rows=ligand_summary_rows, docking_rows=docking_rows,
                lipinski_rows=with_group(lipinski_rows, group_of) or None,
                admet_rows=with_group(admet_rows, group_of) or None, rmsd_rows=rmsd_rows or None,
                replicate_stats_rows=with_group(replicate_stats, group_of) or None,
                group_summary_rows=summarize_groups(lipinski_rows, admet_rows, group_of) or None,
                group_docking_rows=summarize_docking_by_group(replicate_stats, group_of) or None,
                logger=self.log,
            )

            if self.cfg.generate_charts:
                self._generate_charts(replicate_stats, lipinski_rows, admet_rows, group_of)
                self._generate_group_charts(replicate_stats, lipinski_rows, admet_rows, group_of)
            if self.cfg.run_heatmap:
                self._generate_heatmaps(replicate_stats, lipinski_rows, group_of)
            if self.cfg.run_pca:
                self._run_pca(ligand_records, lipinski_rows, admet_rows, group_of)
            if self.cfg.run_hca:
                self._run_hca(ligand_records, lipinski_rows, group_of)

            if self.cfg.gcms_data:
                self._stage("analisis GC-MS")
                self._run_gcms()

            if self._similarity_enabled():
                self._stage("interaksi dan similaritas")
                self._run_interactions_and_similarity()

            self._state.update_progress("selesai", finished=True)
            self.log.info("=== chemflow: pipeline selesai ===")
            self._log_reused_summary()
            if self.failed_ligands:
                self.log.warning(f"Ligan gagal diproses: {self.failed_ligands}")
            if self.failed_receptors:
                self.log.warning(f"Reseptor gagal diproses: {self.failed_receptors}")
            if self.failed_interactions:
                self.log.warning(f"Interaksi BIOVIA gagal diekspor: {self.failed_interactions}")
            return 0
        except KeyboardInterrupt:
            self.log.warning("Dihentikan pengguna (Ctrl+C). Progres yang sudah selesai tersimpan.")
            self._log_resume_hint()
            return 130
        except (ValueError, FileNotFoundError) as exc:
            self.log.error(f"Pipeline dihentikan: {exc}")
            self.log.debug("Detail error:", exc_info=True)
            self._log_resume_hint()
            return 1
        except Exception:
            self.log.exception("Pipeline berhenti karena error fatal.")
            self._log_resume_hint()
            return 1

    def _run_gcms(self) -> None:
        """Analisis GC-MS opsional. Kegagalannya hanya dicatat, hasil docking tidak terpengaruh."""
        from chemflow.gcms import GcmsConfig, run_gcms_analysis

        try:
            config = GcmsConfig(
                data=self.cfg.gcms_data, output_dir=self.cfg.output_dir, groups_file=self.cfg.gcms_groups,
                library=self.cfg.gcms_library, dpi=self.cfg.figure_dpi, figure_formats=self.cfg.figure_formats,
            )
            result = run_gcms_analysis(config, logger=self.log)
            self.log.info(f"Analisis GC-MS selesai: {result.workbook}")
        except (ValueError, FileNotFoundError) as exc:
            self.log.warning(f"Analisis GC-MS dilewati: {exc}")
            self.log.debug("Detail error GC-MS:", exc_info=True)

    def _similarity_enabled(self) -> bool:
        """Similaritas berjalan bila diminta, atau otomatis saat Windows dan BIOVIA terdeteksi."""
        from chemflow.interaction import detect_biovia

        flag = self.cfg.run_similarity
        if flag is not None:
            return flag
        if not self._need_native():
            return False
        executable = detect_biovia(self.cfg.biovia_exe)
        if executable is None:
            self.log.info("Similaritas interaksi dilewati: BIOVIA tidak terdeteksi (butuh Windows dan BIOVIA "
                          "Discovery Studio). Jalankan 'chemflow interactions' bila BIOVIA sudah tersedia.")
            return False
        self.log.info(f"BIOVIA terdeteksi ({executable.name}): similaritas interaksi dijalankan otomatis. "
                      f"Gunakan --no-similarity untuk melewatinya.")
        return True

    def _run_interactions_and_similarity(self) -> None:
        """Ekspor interaksi kompleks lewat BIOVIA, lalu hitung similaritas terhadap native.

        BIOVIA yang tidak bisa dipakai tidak menggagalkan run: similaritas tetap
        dihitung dari berkas interaksi yang sudah ada (mis. hasil ekspor manual).
        """
        from chemflow.interaction import BioviaUnavailableError, export_interactions
        from chemflow.interaction.biovia_gui import BioviaError
        from chemflow.similarity.report import run_similarity_report

        try:
            summary = export_interactions(
                self.cfg.output_dir, self.cfg.interactions_dir, executable=self.cfg.biovia_exe,
                launch_timeout=self.cfg.biovia_launch_timeout, show_progress=self.cfg.show_progress,
                lock_input=self.cfg.lock_input, logger=self.log,
            )
            self.failed_interactions = [f"{job.receptor_key}/{job.stem}" for job, _ in summary.failed]
        except (BioviaUnavailableError, BioviaError, FileNotFoundError) as exc:
            self.log.error(f"Ekspor interaksi BIOVIA dilewati: {exc}")
            self.log.error(f"Similaritas memakai berkas interaksi yang sudah ada di {self.cfg.interactions_dir}.")

        report = run_similarity_report(
            self.cfg.output_dir, interactions_dir=self.cfg.interactions_dir, dpi=self.cfg.figure_dpi,
            formats=self.cfg.figure_formats, max_rows=self.cfg.plot_max_rows, max_cols=self.cfg.plot_max_cols,
            logger=self.log,
        )
        if report.results:
            self.log.info(f"Similaritas interaksi: {len(report.results)} pasangan ligan-reseptor, "
                          f"hasil di {report.workbook}, {len(report.plots)} grafik.")
        else:
            self.log.warning("Tidak ada pasangan yang bisa dihitung similaritasnya (lihat peringatan di atas).")

    def _begin(self) -> None:
        if self._resume:
            self._admet_cache = read_json(self._state.admet_cache_path, {}) or {}
            self._state.save_config(self.cfg)   # simpan override (mis. path obabel) untuk resume berikutnya
            self.log.info("=== chemflow: melanjutkan pipeline dari checkpoint ===")
        else:
            if self._state.is_unfinished():
                self.log.warning(
                    f"Folder output ini berisi run yang belum selesai. Untuk melanjutkannya tanpa mengulang, "
                    f"hentikan proses ini dan jalankan: chemflow resume --output \"{self.cfg.output_dir}\". "
                    f"Melanjutkan run baru akan menimpa progres tersebut."
                )
            self._state.clear_checkpoints()
            self._state.save_config(self.cfg)
            self.log.info("=== chemflow: memulai pipeline ===")
        self._state.update_progress("mulai")

    def _stage(self, name: str) -> None:
        self._state.update_progress(name)

    def _log_resume_hint(self) -> None:
        if self._state.exists():
            self.log.info(f"Lanjutkan dari titik terakhir dengan: chemflow resume --output \"{self.cfg.output_dir}\"")

    def _bump(self, label: str, count: int = 1) -> None:
        """Catat ``count`` item yang dipakai ulang dari checkpoint (untuk ringkasan resume)."""
        if count > 0:
            self._reused[label] = self._reused.get(label, 0) + count

    def _count_reused(self, label: str, results) -> None:
        self._bump(label, sum(1 for r in results if getattr(r, "reused", False)))

    def _log_reused_summary(self) -> None:
        if self._resume and self._reused:
            parts = ", ".join(f"{count} {label}" for label, count in self._reused.items())
            self.log.info(f"Resume: dipakai ulang dari checkpoint: {parts}.")

    def _need_native(self) -> bool:
        return self.cfg.include_native or self.cfg.run_rmsd_validation

    def _group_for(self, name: str) -> str:
        if name in self._group_of:
            return self._group_of[name]
        for record in self._input_records:
            if _file_name(record) == name:
                return group_label(record.group)
        return NO_GROUP

    def _read_and_resolve_ligands(self) -> List[LigandRecord]:
        cache = (read_json(self._state.ligands_path, {}) or {}) if self._resume else {}
        output_length = len(str(self.cfg.output_dir.resolve()))
        name_length = cache.get("name_length") or (
            _name_length_budget(output_length) if os.name == "nt" else _DEFAULT_NAME_LENGTH
        )
        if name_length < _DEFAULT_NAME_LENGTH and not cache.get("name_length"):
            self.log.warning(
                f"Path folder output panjang ({output_length} karakter), nama file ligan dipendekkan "
                f"menjadi maksimal {name_length} karakter agar di bawah batas path Windows. "
                f"Pilih folder output yang lebih pendek untuk nama yang lebih utuh."
            )
        records = read_ligands(
            self.cfg.ligand_excel, name_col=self.cfg.ligand_name_col,
            smiles_col=self.cfg.ligand_smiles_col, group_col=self.cfg.ligand_group_col,
            max_name_length=name_length, logger=self.log,
        )
        self._input_records = list(records)
        self._group_of.update({_file_name(r): group_label(r.group) for r in records})

        saved = {"name_length": name_length, "resolved": dict(cache.get("resolved", {})),
                 "failed": list(cache.get("failed", []))}
        write_json_atomic(self._state.ligands_path, saved)
        if not self.cfg.fetch_missing_smiles:
            return records

        needs_lookup = [r for r in records if r.needs_pubchem_lookup]
        if not needs_lookup:
            return records

        self.log.info(f"Resolusi PubChem untuk {len(needs_lookup)} senyawa tanpa SMILES ...")
        resolver = PubChemResolver(logger=self.log)
        by_name: Dict[str, str] = {}
        resolved: List[LigandRecord] = []
        for r in records:
            if not r.needs_pubchem_lookup:
                resolved.append(r)
                continue
            safe = _file_name(r)
            checkpointed = saved["resolved"].get(safe)
            smiles = checkpointed or by_name.get(r.name.casefold())
            changed = False
            if checkpointed:
                self._bump("SMILES PubChem")
            elif smiles:
                pass  # senyawa yang sama di grup lain, SMILES sudah didapat pada iterasi ini
            elif self._resume and r.name in saved["failed"]:
                self.failed_ligands.append(r.name)
                self.log.warning(f"Melewati '{r.name}': SMILES tak ditemukan pada run sebelumnya.")
                continue
            else:
                smiles = resolver.resolve(r.name)
                if not smiles and self.cfg.interactive_pubchem_fallback:
                    try:
                        smiles = prompt_manual_smiles(r.name)
                    except RuntimeError:
                        pass  # non-TTY: lanjut ke penanganan gagal di bawah, tanpa prompt
                changed = True
            if smiles:
                by_name[r.name.casefold()] = smiles
                if saved["resolved"].get(safe) != smiles:
                    saved["resolved"][safe] = smiles
                    changed = True
                resolved.append(r._replace(smiles=smiles))
            else:
                if r.name not in saved["failed"]:
                    saved["failed"].append(r.name)
                self.failed_ligands.append(r.name)
                self.log.warning(f"Melewati '{r.name}', SMILES tak ditemukan di PubChem.")
            if changed:
                write_json_atomic(self._state.ligands_path, saved)
        return resolved

    def _prepare_ligands(self, records: List[LigandRecord]) -> Dict[str, LigandPrepResult]:
        results: Dict[str, LigandPrepResult] = {}
        reused = 0
        for r in tqdm(records, desc="Preparasi ligan", unit="ligan", disable=not self.cfg.show_progress):
            if not r.smiles:
                continue
            safe_name = _file_name(r)
            try:
                result, was_reused = self._prepare_cached(
                    safe_name, r.smiles, self.cfg.ligand_dir / safe_name, generate_image=self.cfg.generate_2d_image,
                )
                results[safe_name] = result
                reused += 1 if was_reused else 0
            except Exception as exc:
                self.failed_ligands.append(r.name)
                self.log.error(f"Preparasi ligan '{r.name}' gagal: {exc}")
        self._bump("ligan siap", reused)
        self.log.info(f"Ligan siap docking: {len(results)}/{len(records)}")
        return results

    def _prepare_cached(self, name: str, smiles: Optional[str], directory, *,
                        generate_image: bool) -> Tuple[LigandPrepResult, bool]:
        """Preparasi satu ligan dengan checkpoint. Return ``(hasil, dipakai_ulang)``.

        ``smiles=None`` hanya sah pada resume: SMILES diambil dari checkpoint (dipakai ligan native
        agar tidak menurunkan SMILES dari RCSB lagi).
        """
        base = self.cfg.output_dir
        if self._resume:
            cached = load_ligand_prep(directory, base, expected_smiles=smiles)
            if cached is not None:
                result, lipinski = cached
                if lipinski:
                    self._lipinski_by_name[name] = lipinski
                return result, True
        if smiles is None:
            raise ValueError(f"SMILES untuk '{name}' tidak tersedia.")

        result = self._ligand_preparer.prepare(
            name, smiles, directory, force_field=self.cfg.force_field,
            max_iterations=self.cfg.minimize_max_iters, generate_image=generate_image,
        )
        lipinski = self._lipinski_row(name, result)
        try:
            save_ligand_prep(directory, result, lipinski, base)
        except Exception as exc:
            self.log.warning(f"Checkpoint ligan '{name}' gagal ditulis: {exc}")
        return result, False

    def _lipinski_row(self, name: str, result: LigandPrepResult) -> Optional[Dict[str, Any]]:
        mol = getattr(result, "mol", None)
        if mol is None:
            return self._lipinski_by_name.get(name)
        try:
            lip = LipinskiCalculator.calculate(mol)
        except Exception as exc:
            self.log.warning(f"Kalkulasi Lipinski gagal untuk '{name}': {exc}")
            return None
        row = {
            "ligand": name, "MW": lip.molecular_weight, "LogP": lip.logp,
            "HBD": lip.hbd, "HBA": lip.hba, "Lipinski_Violations": lip.violations,
            "Lolos_Ro5": lip.passes_ro5,
        }
        self._lipinski_by_name[name] = row
        return row

    def _compute_lipinski(self, ligand_results: Dict[str, LigandPrepResult]) -> List[Dict[str, Any]]:
        rows = []
        for name, result in ligand_results.items():
            row = self._lipinski_by_name.get(name) or self._lipinski_row(name, result)
            if row:
                rows.append(row)
        return rows

    def _load_admet_from_file(self, ligand_results: Dict[str, LigandPrepResult]) -> List[Dict[str, Any]]:
        names = [_file_name(r) for r in self._input_records]
        smiles = [ligand_results[n].smiles if n in ligand_results else r.smiles
                  for n, r in zip(names, self._input_records)]
        rows = load_admet_rows(self.cfg.admet_file, names, smiles, logger=self.log)
        prepared = [row for row in rows if row["ligand"] in ligand_results]
        self.log.info(f"ADMET dari file: {len(prepared)}/{len(rows)} ligan siap docking punya data ADMET.")
        return prepared

    def _run_admet(self, ligand_results: Dict[str, LigandPrepResult]) -> List[Dict[str, Any]]:
        if self.cfg.admet_file is not None:
            return self._load_admet_from_file(ligand_results)
        return self._scrape_admet([(name, r.smiles) for name, r in ligand_results.items()])

    def _scrape_admet(self, items: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        """Prediksi ADMETLab3 untuk ``(nama, smiles)``; hanya SMILES unik yang dikirim.

        Senyawa yang sama di beberapa grup (SMILES sama) diprediksi sekali lalu hasilnya disalin ke tiap
        ligan menurut indeks saat dikirim. Hasil per SMILES disimpan di ``_state/admet_cache.json``
        sehingga resume hanya mengirim SMILES yang belum ada.
        """
        if not items:
            return []
        names = [name for name, _ in items]
        groups = [self._group_for(name) for name in names]
        grouping = group_by_smiles([s for _, s in items], names)
        if grouping.n_duplicates:
            self.log.info(
                f"ADMET: {len(items)} ligan = {len(grouping.unique_smiles)} SMILES unik; hasil disalin ke "
                f"{grouping.n_duplicates} ligan kembar (senyawa multi-grup): "
                + "; ".join(describe_duplicates(grouping, names, groups))
            )

        pending = [s for s in grouping.unique_smiles if s not in self._admet_cache]
        cached = len(grouping.unique_smiles) - len(pending)
        if cached:
            self._bump("SMILES ADMET", cached)
            self.log.info(f"ADMET: {cached} SMILES sudah ada di checkpoint, {len(pending)} dikirim ke ADMETLab3.")

        if pending:
            scraper = AdmetLabScraper(max_batch_size=self.cfg.admet_batch_size,
                                       ssl_verify=self.cfg.admet_ssl_verify, logger=self.log)
            batch_size = self.cfg.admet_batch_size
            starts = list(range(0, len(pending), batch_size))
            for i in tqdm(starts, desc="ADMET (ADMETLab3)", unit="batch", disable=not self.cfg.show_progress):
                batch = pending[i:i + batch_size]
                mapped = self._map_admet_batch(batch, scraper.run(batch), number=i // batch_size + 1)
                self._admet_cache.update(mapped)
                write_json_atomic(self._state.admet_cache_path, self._admet_cache)

        unique_rows = [self._admet_cache.get(s) for s in grouping.unique_smiles]
        rows = fan_out(unique_rows, grouping, names, groups)
        self.log.info(f"ADMET diperoleh untuk {len(rows)}/{len(items)} senyawa.")
        return rows

    def _map_admet_batch(self, batch: List[str], df, number: int) -> Dict[str, Dict[str, Any]]:
        """Petakan baris hasil ADMETLab3 ke SMILES yang dikirim (posisional, cadangan lewat ``raw_smiles``)."""
        if df.empty:
            self.log.warning(f"Batch ADMET {number} tidak mengembalikan data.")
            return {}
        records = [{str(k): _json_value(v) for k, v in row.items()} for _, row in df.iterrows()]
        if len(records) == len(batch):
            return dict(zip(batch, records))

        by_raw = {str(r.get("raw_smiles")): r for r in reversed(records) if r.get("raw_smiles") is not None}
        if by_raw and all(s in by_raw for s in batch):
            self.log.info(f"Batch ADMET {number}: jumlah baris tak sama, dicocokkan lewat kolom raw_smiles.")
            return {s: by_raw[s] for s in batch}
        self.log.warning(
            f"Batch ADMET {number}: jumlah baris hasil ({len(records)}) tidak cocok dengan jumlah senyawa "
            f"terkirim ({len(batch)}), korespondensi tidak bisa dipercaya, batch ini dilewati demi integritas data."
        )
        return {}

    def _prepare_receptors(self):
        entries = read_receptors(
            self.cfg.receptor_excel, pdb_col=self.cfg.receptor_pdb_col,
            cx_col=self.cfg.receptor_cx_col, cy_col=self.cfg.receptor_cy_col, cz_col=self.cfg.receptor_cz_col,
            sx_col=self.cfg.receptor_sx_col, sy_col=self.cfg.receptor_sy_col, sz_col=self.cfg.receptor_sz_col,
            logger=self.log,
        )

        targets: List[ReceptorDockingTarget] = []
        rmsd_context: Dict[str, Any] = {}
        base = self.cfg.output_dir
        reused = 0

        for entry in tqdm(entries, desc="Preparasi reseptor", unit="reseptor", disable=not self.cfg.show_progress):
            rec_dir = self.cfg.receptor_dir / entry.unique_key
            try:
                cached = load_receptor(rec_dir, base) if self._resume else None
                if cached is not None:
                    target, native = cached
                    reused += 1
                else:
                    fetched = fetch_pdb(entry.pdb_code, self.cfg.receptor_dir / "_pdb_cache", logger=self.log)
                    grid_box, native = self._resolve_gridbox(entry, fetched)

                    mol = self._receptor_preparer.load(fetched.pdb_path)
                    docking_pdbqt = self._receptor_preparer.prepare_for_docking(
                        mol, rec_dir / f"{entry.unique_key}_docking.pdbqt",
                        remove_waters=self.cfg.remove_waters, remove_hetero_ligands=self.cfg.remove_hetero_ligands,
                        keep_metals=self.cfg.keep_metals,
                    )
                    clean_pdb = self._receptor_preparer.prepare_for_merge(
                        mol, rec_dir / f"{entry.unique_key}_clean.pdb",
                        remove_waters=self.cfg.remove_waters, remove_hetero_ligands=self.cfg.remove_hetero_ligands,
                        keep_metals=self.cfg.keep_metals,
                    )
                    target = ReceptorDockingTarget(
                        key=entry.unique_key, pdb_code=entry.pdb_code,
                        receptor_pdbqt=docking_pdbqt, receptor_clean_pdb=clean_pdb, grid_box=grid_box,
                    )
                    try:
                        save_receptor(rec_dir, target, native, base)
                    except Exception as exc:
                        self.log.warning(f"Checkpoint reseptor '{entry.unique_key}' gagal ditulis: {exc}")

                targets.append(target)
                if native is not None:
                    rmsd_context[entry.unique_key] = {"native": native, "grid_box": target.grid_box,
                                                       "receptor_pdbqt": target.receptor_pdbqt}
            except Exception as exc:
                self.failed_receptors.append(entry.pdb_code)
                self.log.error(f"Preparasi reseptor '{entry.pdb_code}' gagal: {exc}")

        self._bump("reseptor", reused)
        self.log.info(f"Reseptor siap docking: {len(targets)}/{len(entries)}")
        return targets, rmsd_context

    def _nearest_native(self, entry, fetched) -> Optional[NativeLigand]:
        """Ligan native terdekat dari pusat gridbox Excel, bila cukup dekat untuk dianggap situs yang sama."""
        if not fetched.native_ligands:
            return None

        def distance(lig: NativeLigand) -> float:
            return math.sqrt((lig.center_x - entry.center_x) ** 2 + (lig.center_y - entry.center_y) ** 2
                             + (lig.center_z - entry.center_z) ** 2)

        nearest = min(fetched.native_ligands, key=distance)
        gap = distance(nearest)
        if gap > self.cfg.native_match_radius:
            self.log.warning(
                f"Ligan native terdekat '{nearest.label}' berjarak {gap:.1f} A dari pusat gridbox "
                f"'{entry.unique_key}' (batas {self.cfg.native_match_radius:g} A), dianggap bukan situs yang "
                f"sama sehingga tidak dipakai sebagai referensi maupun untuk menurunkan ukuran kotak."
            )
            return None
        return nearest

    def _resolve_gridbox(self, entry, fetched):
        """Tentukan gridbox reseptor. Return ``(GridBox, ligan_native_atau_None)``.

        Ukuran kotak yang tidak diberikan diturunkan dari ligan native (kubus: ekstensi + ``box_padding``),
        bukan angka tetap; ``default_box_size`` hanya cadangan bila tak ada native.
        """
        need_native = self._need_native()
        if entry.has_gridbox_center:
            native = self._nearest_native(entry, fetched)
            if need_native and not fetched.native_ligands:
                self.log.warning(
                    f"Ligan native diperlukan (analitik native / validasi RMSD) untuk '{entry.pdb_code}' tapi "
                    f"tidak ada ligan native terdeteksi di struktur ini, dilewati untuk reseptor ini."
                )

            explicit = (entry.size_x or entry.uniform_size, entry.size_y or entry.uniform_size,
                        entry.size_z or entry.uniform_size)
            if native is not None:
                fallback = GridBox.suggested_size(native.extent, self.cfg.box_padding)
                source = (f"ligan native {native.label} (ekstensi {native.extent:.1f} A + "
                          f"padding {self.cfg.box_padding:g} A)")
            else:
                fallback, source = self.cfg.default_box_size, "ukuran default"
            if any(size is None for size in explicit):
                self.log.info(f"Ukuran gridbox '{entry.unique_key}' tidak lengkap di Excel, kekurangannya "
                              f"diisi {fallback:g} A dari {source}.")

            sx, sy, sz = (size or fallback for size in explicit)
            box = GridBox.from_manual(entry.center_x, entry.center_y, entry.center_z, sx, sy, sz,
                                      ref_label=native.label if native else None)
            return box, (native if need_native else None)

        if self.cfg.interactive_gridbox:
            cx, cy, cz, sx, sy, sz, native = interactive_select_native_ligand(
                fetched, default_size=(self.cfg.default_box_size,) * 3, padding=self.cfg.box_padding,
            )
            return GridBox.from_manual(cx, cy, cz, sx, sy, sz, ref_label=native.label if native else None), native

        raise ValueError(
            f"Reseptor '{entry.pdb_code}' tidak punya gridbox eksplisit di Excel dan mode interaktif "
            f"dimatikan, tidak ada cara menentukan lokasi docking."
        )

    def _prepare_natives(self, rmsd_context, targets) -> List[NativeEntry]:
        """Siapkan tiap ligan native sebagai ligan referensi (SMILES, preparasi 3D, Lipinski)."""
        if not self._need_native() or not rmsd_context:
            return []
        target_keys = {t.key for t in targets}
        used = {name.lower() for name in self._group_of}
        entries: List[NativeEntry] = []

        for key, ctx in rmsd_context.items():
            if key not in target_keys:
                continue
            native: NativeLigand = ctx["native"]
            base_name = f"NATIVE_{sanitize_filename(native.label)}"
            name = base_name if base_name.lower() not in used else f"{base_name}_{sanitize_filename(key)}"
            used.add(name.lower())
            directory = self.cfg.ligand_dir / name
            try:
                # Saat resume dengan checkpoint utuh, SMILES diambil dari checkpoint (tanpa unduh templat RCSB).
                has_checkpoint = self._resume and load_ligand_prep(directory, self.cfg.output_dir) is not None
                smiles = None if has_checkpoint else derive_native_smiles(
                    native.to_pdb_block(), native.resname, self.cfg.cache_dir / "ligand_templates", self.log,
                )
                prep, was_reused = self._prepare_cached(name, smiles, directory, generate_image=False)
                if was_reused:
                    self._bump("ligan native")
                entries.append(NativeEntry(
                    name=name, label=native.label, receptor_key=key, smiles=prep.smiles, prep=prep,
                    lipinski=self._lipinski_by_name.get(name),
                ))
            except Exception as exc:
                self._native_errors[key] = str(exc)
                self.log.warning(f"Preparasi ligan native '{native.label}' (reseptor '{key}') gagal: {exc}")
        return entries

    def _dock_natives(self, orchestrator: DockingOrchestrator, targets) -> List[DockingRunResult]:
        """Redock tiap native ke reseptornya sendiri dengan parameter sama seperti ligan uji."""
        if not self._natives:
            return []
        target_by_key = {t.key: t for t in targets}
        results: List[DockingRunResult] = []
        for entry in tqdm(self._natives, desc="Docking ligan native", unit="native",
                          disable=not self.cfg.show_progress):
            results.extend(orchestrator.run_matrix(
                {entry.name: entry.prep.pdbqt_path}, [target_by_key[entry.receptor_key]], self.cfg.docking_dir,
                n_replicates=self.cfg.n_replicates, exhaustiveness=self.cfg.exhaustiveness,
                num_modes=self.cfg.num_modes, energy_range=self.cfg.energy_range, base_seed=self.cfg.seed,
                show_progress=False, resume=self._resume,
            ))
        self._count_reused("run native", results)
        return results

    def _native_properties(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Baris Lipinski dan ADMET ligan native (kosong bila native tak ikut analitik)."""
        if not (self.cfg.include_native and self._natives):
            return [], []
        for entry in self._natives:
            self._group_of[entry.name] = NATIVE_GROUP
        lipinski = [entry.lipinski for entry in self._natives if entry.lipinski]

        admet: List[Dict[str, Any]] = []
        if self.cfg.run_admet:
            if self.cfg.admet_file is not None:
                self.log.info("ADMET ligan native dilewati: mode --admet-file hanya memetakan ligan uji.")
            else:
                admet = self._scrape_admet([(entry.name, entry.smiles) for entry in self._natives])
        return lipinski, admet

    def _run_rmsd_validation(self, rmsd_context, native_results: List[DockingRunResult]) -> List[Dict[str, Any]]:
        """RMSD pose native hasil redocking terhadap struktur kristal (pose terbaik lintas replikat)."""
        validator = RedockingValidator(self.cfg.rmsd_threshold_good, self.cfg.rmsd_threshold_acceptable,
                                        logger=self.log)
        entry_by_key = {e.receptor_key: e for e in self._natives}
        rows: List[Dict[str, Any]] = []

        for key, ctx in tqdm(list(rmsd_context.items()), desc="Validasi RMSD redocking", unit="reseptor",
                              disable=not self.cfg.show_progress):
            native = ctx["native"]
            try:
                entry = entry_by_key.get(key)
                if entry is None:
                    raise ValueError(self._native_errors.get(key, "Ligan native tidak berhasil disiapkan."))
                runs = [r for r in native_results if r.ligand_name == entry.name and r.receptor_key == key]
                good = [r for r in runs if r.success]
                if not good:
                    detail = next((r.error for r in runs if r.error), "Redocking tidak menghasilkan pose.")
                    raise ValueError(detail)
                best = min(good, key=lambda r: r.best_affinity)

                pose_mols = read_pdbqt(best.output_pdbqt, logger=self.log)
                if not pose_mols:
                    raise ValueError("Pose redocking tidak terbaca dari PDBQT.")

                result = validator.validate(native.to_pdb_block(), pose_mols[0], native.label)
                rows.append({
                    "receptor": key, "native_ligand": native.label,
                    "rmsd_angstrom": result.rmsd, "status": result.status,
                    "redock_affinity": best.best_affinity,
                    "metode": result.method, "catatan": result.note,
                })
            except Exception as exc:
                self.log.warning(f"Validasi RMSD gagal untuk reseptor '{key}': {exc}")
                rows.append({"receptor": key, "native_ligand": native.label,
                              "rmsd_angstrom": None, "status": "gagal", "redock_affinity": None,
                              "metode": "-", "catatan": str(exc)})

        return rows

    @staticmethod
    def _is_merged(path) -> bool:
        """Kompleks selesai bila PDB dan sidecar JSON-nya (ditulis paling akhir) ada."""
        return path.exists() and path.with_suffix(".json").exists()

    def _merge_native_reference(self, rmsd_context, targets) -> None:
        """Merge pose kristalografi asli ligan native (bukan hasil docking) ke
        kompleks referensi baseline, dipakai analisis similaritas interaksi."""
        from rdkit import Chem

        if not rmsd_context:
            return
        target_by_key = {t.key: t for t in targets}
        for key, ctx in tqdm(list(rmsd_context.items()), desc="Merge referensi native", unit="reseptor",
                              disable=not self.cfg.show_progress):
            target = target_by_key.get(key)
            if target is None:
                continue
            native = ctx["native"]
            try:
                out_path = self.cfg.complex_dir / target.key / f"NATIVE_{sanitize_filename(native.label)}_complex.pdb"
                if self._resume and self._is_merged(out_path):
                    continue
                clean_receptor = Chem.MolFromPDBFile(str(target.receptor_clean_pdb), sanitize=True, removeHs=False)
                native_mol = Chem.MolFromPDBBlock(native.to_pdb_block(), sanitize=True, removeHs=False)
                if clean_receptor is None or native_mol is None:
                    continue
                merge_complex(clean_receptor, native_mol, out_path, ligand_name=native.label,
                              is_native=True, logger=self.log)
            except Exception as exc:
                self.log.warning(f"Merge referensi native gagal untuk reseptor '{key}': {exc}")

    def _merge_poses(self, docking_results, targets, skip_ligands: Set[str] = frozenset()) -> None:
        """Merge pose docking ke kompleks reseptor bersih.

        ``self.cfg.merge_mode``:
            - ``"best"``: satu file per (ligan, reseptor), pose dari replikat
              dengan afinitas terbaik secara global (bukan diasumsikan replikat 1).
            - ``"all"``: satu file per pose per replikat sukses, semua di-merge.

        ``skip_ligands``: nama ligan yang tidak di-merge. Hasil docking ligan native tidak boleh
        di-merge karena namanya bentrok dengan kompleks kristal referensi native.
        Saat resume, kompleks yang sudah lengkap dan berasal dari run yang dipakai ulang dilewati.
        """
        from rdkit import Chem

        target_by_key = {t.key: t for t in targets}
        candidates = [r for r in docking_results if r.success and r.ligand_name not in skip_ligands]

        if self.cfg.merge_mode == "best":
            best_by_pair: Dict[Any, Any] = {}
            for r in candidates:
                pair_key = (r.ligand_name, r.receptor_key)
                current = best_by_pair.get(pair_key)
                if current is None or r.best_affinity < current.best_affinity:
                    best_by_pair[pair_key] = r
            selected = list(best_by_pair.values())
        else:
            selected = candidates

        skipped = 0
        for r in tqdm(selected, desc="Merge kompleks", unit="pose", disable=not self.cfg.show_progress):
            target = target_by_key.get(r.receptor_key)
            if target is None:
                continue
            try:
                stem = sanitize_filename(r.ligand_name)
                if self.cfg.merge_mode == "best":
                    out_path = self.cfg.complex_dir / target.key / f"{stem}_complex.pdb"
                else:
                    out_path = (self.cfg.complex_dir / target.key /
                                f"{stem}_rep{r.replicate:02d}_mode{max(len(r.poses), 1):02d}_complex.pdb")
                if self._resume and r.reused and self._is_merged(out_path):
                    skipped += 1
                    continue

                clean_receptor = Chem.MolFromPDBFile(str(target.receptor_clean_pdb), sanitize=True, removeHs=False)
                pose_mols = read_pdbqt(r.output_pdbqt, logger=self.log)
                if clean_receptor is None or not pose_mols:
                    continue

                if self.cfg.merge_mode == "best":
                    merge_complex(clean_receptor, pose_mols[0], out_path, ligand_name=r.ligand_name, logger=self.log)
                else:
                    for mode_idx, pose_mol in enumerate(pose_mols, start=1):
                        mode_path = (self.cfg.complex_dir / target.key /
                                     f"{stem}_rep{r.replicate:02d}_mode{mode_idx:02d}_complex.pdb")
                        merge_complex(clean_receptor, pose_mol, mode_path, ligand_name=r.ligand_name, logger=self.log)
            except Exception as exc:
                self.log.warning(f"Merge gagal untuk '{r.ligand_name}'x'{r.receptor_key}' rep{r.replicate}: {exc}")
        self._bump("kompleks", skipped)

    def _docking_rows(self, docking_results) -> List[Dict[str, Any]]:
        rows = []
        for r in docking_results:
            rows.append({
                "ligand": r.ligand_name, "receptor": r.receptor_key, "replicate": r.replicate,
                "seed": r.seed, "affinity_best": r.best_affinity, "n_poses": len(r.poses),
                "status": "sukses" if r.success else "gagal", "error": r.error or "",
            })
        return rows

    def _ligand_summary_rows(self, records, results) -> List[Dict[str, Any]]:
        rows = []
        for r in records:
            safe_name = _file_name(r)
            rows.append({
                "name": r.name, "nama_file": safe_name, "smiles": r.smiles, "group": r.group or "",
                "tipe": "uji", "status": "siap" if safe_name in results else "gagal",
            })
        if self.cfg.include_native:
            for entry in self._natives:
                rows.append({
                    "name": entry.label, "nama_file": entry.name, "smiles": entry.smiles,
                    "group": NATIVE_GROUP, "tipe": "native", "status": "siap",
                })
        return rows

    def _generate_charts(self, replicate_stats, lipinski_rows, admet_rows,
                         group_of: Optional[Dict[str, str]] = None) -> None:
        if not replicate_stats:
            return
        group_of = group_of or {}
        builder = ChartBuilder(self.cfg.analytics_dir, dpi=self.cfg.figure_dpi,
                               formats=self.cfg.figure_formats, logger=self.log,
                               max_rows=self.cfg.plot_max_rows)

        multi_receptor = len({r["receptor"] for r in replicate_stats}) > 1

        def _display_label(row) -> str:
            return f'{row["ligand"]} ({row["receptor"]})' if multi_receptor else row["ligand"]

        labeled_stats = [{**r, "_display_label": _display_label(r)} for r in replicate_stats]
        native_labels = {r["_display_label"] for r in labeled_stats if group_of.get(r["ligand"]) == NATIVE_GROUP}
        builder.bar_affinity(labeled_stats, ligand_key="_display_label", value_key="affinity_best",
                             highlight_keys=native_labels)

        lipinski_by_name = {r["ligand"]: r for r in lipinski_rows}
        admet_scores = {r["ligand"]: category_scores(r) for r in (admet_rows or [])}

        combined = []
        for row in labeled_stats:
            merged = dict(row)
            merged.update(lipinski_by_name.get(row["ligand"], {}))
            merged.update(admet_scores.get(row["ligand"], {}))
            combined.append(merged)

        criteria = ["affinity_best"]
        labels = {"affinity_best": "ΔG docking"}
        title_parts = []

        if lipinski_rows:
            criteria += ["MW", "LogP", "HBD", "HBA"]
            title_parts.append("Fisikokimia")

        admet_criteria = sorted({k for scores in admet_scores.values() for k in scores},
                                key=lambda c: list(CATEGORIES).index(c))
        if admet_criteria:
            criteria += admet_criteria
            labels.update({c: f"ADMET {c}" for c in admet_criteria})
            title_parts.append("ADMET")

        title_parts.append("ΔG")
        title = "Profil Gabungan: " + " + ".join(title_parts)

        best_per_ligand: Dict[str, Dict[str, Any]] = {}
        for row in combined:
            if not all(row.get(c) is not None for c in criteria):
                continue
            current = best_per_ligand.get(row["ligand"])
            if current is None or row["affinity_best"] < current["affinity_best"]:
                best_per_ligand[row["ligand"]] = row

        if best_per_ligand:
            builder.radar_combined(
                list(best_per_ligand.values()), criteria=criteria, label_key="_display_label", title=title,
                lower_is_better=[c for c in ("affinity_best", "MW", "LogP", "HBD", "HBA") if c in criteria],
                absolute=admet_criteria, criteria_labels=labels, rank_by="affinity_best",
                pinned={r["_display_label"] for r in best_per_ligand.values()
                        if group_of.get(r["ligand"]) == NATIVE_GROUP},
            )

        if admet_rows:
            pinned_names = {r["ligand"] for r in admet_rows if group_of.get(r["ligand"]) == NATIVE_GROUP}
            builder.radar_all_admet_categories(admet_rows, label_key="ligand", pinned=pinned_names)
            builder.admet_all_stacked_bars(admet_rows)

    def _generate_group_charts(self, replicate_stats, lipinski_rows, admet_rows,
                               group_of: Optional[Dict[str, str]] = None) -> None:
        """Grafik perbandingan antar-grup (ADMET, ΔG, fisikokimia) dengan grup Native sebagai pembanding."""
        group_of = group_of or {}
        if not group_of:
            return
        try:
            builder = GroupChartBuilder(
                self.cfg.analytics_dir, dpi=self.cfg.figure_dpi, formats=self.cfg.figure_formats,
                logger=self.log, max_rows=self.cfg.plot_max_rows, max_cols=self.cfg.plot_max_cols,
            )
            builder.plot_all(replicate_stats, lipinski_rows, admet_rows, group_of)
        except Exception as exc:
            self.log.warning(f"Grafik per grup dilewati: {exc}")
            self.log.debug("Detail error:", exc_info=True)

    def _descriptor_matrix(self, records, lipinski_rows, feature_cols, group_of: Optional[Dict[str, str]] = None):
        group_by_name = {_file_name(r): group_label(r.group) for r in records}
        group_by_name.update(group_of or {})
        lip_by_name = {r["ligand"]: r for r in lipinski_rows}

        matrix, labels, groups = [], [], []
        for name, lip in lip_by_name.items():
            matrix.append([lip[c] for c in feature_cols])
            labels.append(name)
            groups.append(group_by_name.get(name, NO_GROUP))
        return matrix, labels, groups

    def _run_pca(self, records, lipinski_rows, admet_rows, group_of: Optional[Dict[str, str]] = None) -> None:
        feature_cols = ["MW", "LogP", "HBD", "HBA"]
        matrix, labels, groups = self._descriptor_matrix(records, lipinski_rows, feature_cols, group_of)

        try:
            pca = ChemometricPCA(logger=self.log)
            result = pca.compute(matrix, feature_cols, labels, groups)
            pca.plot_2d(result, self.cfg.analytics_dir / "pca_2d.png",
                        dpi=self.cfg.figure_dpi, formats=self.cfg.figure_formats)
            pca.plot_3d(result, self.cfg.analytics_dir / "pca_3d.png",
                        dpi=self.cfg.figure_dpi, formats=self.cfg.figure_formats)
            self.log.info("PCA kemometrik berhasil dibuat.")
        except ValueError as exc:
            self.log.warning(f"PCA dilewati: {exc}")

    def _run_hca(self, records, lipinski_rows, group_of: Optional[Dict[str, str]] = None) -> None:
        feature_cols = ["MW", "LogP", "HBD", "HBA"]
        matrix, labels, groups = self._descriptor_matrix(records, lipinski_rows, feature_cols, group_of)

        try:
            hca = HierarchicalClustering(logger=self.log)
            result = hca.compute(matrix, labels, groups)
            hca.plot_dendrogram(result, self.cfg.analytics_dir / "hca_dendrogram.png",
                                dpi=self.cfg.figure_dpi, formats=self.cfg.figure_formats,
                                max_leaves=self.cfg.plot_max_rows)
            self.log.info("HCA (dendrogram) berhasil dibuat.")
        except ValueError as exc:
            self.log.warning(f"HCA dilewati: {exc}")

    def _generate_heatmaps(self, replicate_stats, lipinski_rows,
                           group_of: Optional[Dict[str, str]] = None) -> None:
        group_of = group_of or {}
        builder = HeatmapBuilder(self.cfg.analytics_dir, dpi=self.cfg.figure_dpi,
                                 formats=self.cfg.figure_formats, logger=self.log,
                                 max_rows=self.cfg.plot_max_rows, max_cols=self.cfg.plot_max_cols)
        if replicate_stats:
            native_rows = [r for r in replicate_stats if group_of.get(r["ligand"]) == NATIVE_GROUP]
            test_rows = [r for r in replicate_stats if group_of.get(r["ligand"]) != NATIVE_GROUP]
            builder.heatmap_affinity(test_rows or replicate_stats, native_rows=native_rows or None,
                                     col_groups=group_of or None)
        if lipinski_rows:
            builder.heatmap_properties(lipinski_rows, properties=["MW", "LogP", "HBD", "HBA"],
                                        filename="heatmap_fisikokimia.png",
                                        title="Heatmap Fisikokimia (Ligan x Parameter)",
                                        row_groups=group_of or None)
            builder.heatmap_properties_clustered(
                lipinski_rows, properties=["MW", "LogP", "HBD", "HBA"],
                filename="heatmap_fisikokimia_klaster.png",
                title="Heatmap Fisikokimia Terklaster (Ligan x Parameter)",
                row_groups=group_of or None,
            )
