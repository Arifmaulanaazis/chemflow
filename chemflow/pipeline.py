"""
Orkestrator utama pipeline chemflow. Menjalankan seluruh tahap secara
berurutan: baca Excel -> resolusi SMILES -> preparasi ligan -> ADMET ->
preparasi reseptor -> docking (matriks + replikasi) -> validasi RMSD ->
merge kompleks -> ekspor hasil -> analitik (chart + PCA).

Kegagalan pada satu ligan/reseptor TIDAK menghentikan seluruh run.
Dicatat sebagai warning/error dan dilaporkan di ringkasan akhir, sisanya
tetap diproses (filosofi yang sama dipakai konsisten di semua modul
chemflow: tahap kosmetik/individual boleh gagal, tahap yang benar-benar
fatal untuk 1 item saja menghentikan proses item itu saja).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from tqdm import tqdm

from chemflow.admet.admet_file import load_admet_rows
from chemflow.admet.admet_rules import CATEGORIES, category_scores
from chemflow.admet.admetlab_scraper import AdmetLabScraper
from chemflow.analytics.charts import ChartBuilder
from chemflow.analytics.hca import HierarchicalClustering
from chemflow.analytics.heatmap import HeatmapBuilder
from chemflow.analytics.pca import ChemometricPCA
from chemflow.chem.descriptors import LipinskiCalculator
from chemflow.chem.ligand_preparer import LigandPreparer, LigandPrepResult
from chemflow.chem.mol_converter import OpenBabelConverter
from chemflow.chem.pubchem_client import PubChemResolver, prompt_manual_smiles
from chemflow.chem.receptor_preparer import ReceptorPreparer
from chemflow.config import PipelineConfig
from chemflow.docking.docking_matrix import (
    DockingOrchestrator, ReceptorDockingTarget, compute_replicate_stats,
)
from chemflow.docking.grid_box import GridBox
from chemflow.docking.merge import merge_complex
from chemflow.docking.rmsd_validation import RedockingValidator
from chemflow.docking.vina_manager import VinaReleaseManager
from chemflow.docking.vina_runner import VinaRunner, resolve_vina_executable
from chemflow.io.excel_ligands import LigandRecord, read_ligands
from chemflow.io.excel_receptors import read_receptors
from chemflow.io.ligand_template import native_smiles as derive_native_smiles
from chemflow.io.pdb_fetcher import fetch_pdb, interactive_select_native_ligand
from chemflow.io.pdbqt_reader import read_pdbqt
from chemflow.io.result_exporter import export_results
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


class Pipeline:
    """Menjalankan seluruh alur chemflow dari konfigurasi yang sudah divalidasi."""

    def __init__(self, config: PipelineConfig) -> None:
        self.cfg = config
        self.log = setup_logging(self.cfg.output_dir / "chemflow.log",
                                  level=getattr(logging, self.cfg.log_level, logging.INFO))
        self._obabel = OpenBabelConverter(self.cfg.openbabel_path, logger=self.log)
        self._ligand_preparer = LigandPreparer(self._obabel, logger=self.log)
        self._receptor_preparer = ReceptorPreparer(
            kollman_fallback="zero" if self.cfg.kollman_fallback_zero else "gasteiger", logger=self.log,
        )
        self._vina_manager = VinaReleaseManager(cache_dir=self.cfg.cache_dir / "vina", logger=self.log)

        self.failed_ligands: List[str] = []
        self.failed_receptors: List[str] = []
        self._input_records: List[LigandRecord] = []

    def run(self) -> int:
        """Jalankan seluruh pipeline. Return 0 sukses, 1 jika gagal total (fatal)."""
        try:
            self.log.info("=== chemflow: memulai pipeline ===")

            ligand_records = self._read_and_resolve_ligands()
            ligand_results = self._prepare_ligands(ligand_records)
            lipinski_rows = self._compute_lipinski(ligand_results)
            admet_rows = self._run_admet(ligand_results) if self.cfg.run_admet else []

            vina_exe = resolve_vina_executable(self._vina_manager, version=self.cfg.vina_version,
                                                explicit_path=self.cfg.vina_executable)
            vina_runner = VinaRunner(vina_exe, logger=self.log)
            orchestrator = DockingOrchestrator(vina_runner, logger=self.log)

            targets, rmsd_context = self._prepare_receptors()
            ligand_pdbqt_map = {name: r.pdbqt_path for name, r in ligand_results.items()}

            docking_results = orchestrator.run_matrix(
                ligand_pdbqt_map, targets, self.cfg.docking_dir,
                n_replicates=self.cfg.n_replicates, exhaustiveness=self.cfg.exhaustiveness,
                num_modes=self.cfg.num_modes, energy_range=self.cfg.energy_range, base_seed=self.cfg.seed,
                show_progress=self.cfg.show_progress,
            )
            replicate_stats = compute_replicate_stats(docking_results)

            rmsd_rows = []
            if self.cfg.run_rmsd_validation and rmsd_context:
                rmsd_rows = self._run_rmsd_validation(rmsd_context, targets, orchestrator, vina_runner)

            self._merge_native_reference(rmsd_context, targets)
            self._merge_poses(docking_results, targets)

            docking_rows = self._docking_rows(docking_results)
            ligand_summary_rows = self._ligand_summary_rows(ligand_records, ligand_results)

            export_path = self.cfg.output_dir / "hasil_chemflow.xlsx"
            export_results(
                export_path, ligand_summary_rows=ligand_summary_rows, docking_rows=docking_rows,
                lipinski_rows=lipinski_rows, admet_rows=admet_rows or None, rmsd_rows=rmsd_rows or None,
                replicate_stats_rows=replicate_stats or None, logger=self.log,
            )

            if self.cfg.generate_charts:
                self._generate_charts(replicate_stats, lipinski_rows, admet_rows)
            if self.cfg.run_heatmap:
                self._generate_heatmaps(replicate_stats, lipinski_rows)
            if self.cfg.run_pca:
                self._run_pca(ligand_records, lipinski_rows, admet_rows)
            if self.cfg.run_hca:
                self._run_hca(ligand_records, lipinski_rows)

            self.log.info("=== chemflow: pipeline selesai ===")
            if self.failed_ligands:
                self.log.warning(f"Ligan gagal diproses: {self.failed_ligands}")
            if self.failed_receptors:
                self.log.warning(f"Reseptor gagal diproses: {self.failed_receptors}")
            return 0
        except (ValueError, FileNotFoundError) as exc:
            self.log.error(f"Pipeline dihentikan: {exc}")
            self.log.debug("Detail error:", exc_info=True)
            return 1
        except Exception:
            self.log.exception("Pipeline berhenti karena error fatal.")
            return 1


    def _read_and_resolve_ligands(self) -> List[LigandRecord]:
        output_length = len(str(self.cfg.output_dir.resolve()))
        name_length = _name_length_budget(output_length) if os.name == "nt" else _DEFAULT_NAME_LENGTH
        if name_length < _DEFAULT_NAME_LENGTH:
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
        if not self.cfg.fetch_missing_smiles:
            return records

        needs_lookup = [r for r in records if r.needs_pubchem_lookup]
        if not needs_lookup:
            return records

        self.log.info(f"Resolusi PubChem untuk {len(needs_lookup)} senyawa tanpa SMILES ...")
        resolver = PubChemResolver(logger=self.log)
        resolved: List[LigandRecord] = []
        for r in records:
            if r.needs_pubchem_lookup:
                smiles = resolver.resolve(r.name)
                if not smiles and self.cfg.interactive_pubchem_fallback:
                    try:
                        smiles = prompt_manual_smiles(r.name)
                    except RuntimeError:
                        pass  # non-TTY: lanjut ke penanganan gagal di bawah, tanpa prompt
                if smiles:
                    resolved.append(r._replace(smiles=smiles))
                else:
                    self.failed_ligands.append(r.name)
                    self.log.warning(f"Melewati '{r.name}', SMILES tak ditemukan di PubChem.")
            else:
                resolved.append(r)
        return resolved

    def _prepare_ligands(self, records: List[LigandRecord]) -> Dict[str, LigandPrepResult]:
        results: Dict[str, LigandPrepResult] = {}
        for r in tqdm(records, desc="Preparasi ligan", unit="ligan", disable=not self.cfg.show_progress):
            if not r.smiles:
                continue
            safe_name = _file_name(r)
            try:
                result = self._ligand_preparer.prepare(
                    safe_name, r.smiles, self.cfg.ligand_dir / safe_name,
                    force_field=self.cfg.force_field, max_iterations=self.cfg.minimize_max_iters,
                    generate_image=self.cfg.generate_2d_image,
                )
                results[safe_name] = result
            except Exception as exc:
                self.failed_ligands.append(r.name)
                self.log.error(f"Preparasi ligan '{r.name}' gagal: {exc}")
        self.log.info(f"Ligan siap docking: {len(results)}/{len(records)}")
        return results

    def _compute_lipinski(self, ligand_results: Dict[str, LigandPrepResult]) -> List[Dict[str, Any]]:
        rows = []
        for name, result in ligand_results.items():
            try:
                lip = LipinskiCalculator.calculate(result.mol)
                rows.append({
                    "ligand": name, "MW": lip.molecular_weight, "LogP": lip.logp,
                    "HBD": lip.hbd, "HBA": lip.hba, "Lipinski_Violations": lip.violations,
                    "Lolos_Ro5": lip.passes_ro5,
                })
            except Exception as exc:
                self.log.warning(f"Kalkulasi Lipinski gagal untuk '{name}': {exc}")
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

        pairs = [(name, r.smiles) for name, r in ligand_results.items()]
        if not pairs:
            return []

        scraper = AdmetLabScraper(max_batch_size=self.cfg.admet_batch_size,
                                   ssl_verify=self.cfg.admet_ssl_verify, logger=self.log)
        rows: List[Dict[str, Any]] = []
        batch_size = self.cfg.admet_batch_size
        batch_starts = list(range(0, len(pairs), batch_size))
        for i in tqdm(batch_starts, desc="ADMET (ADMETLab3)", unit="batch", disable=not self.cfg.show_progress):
            batch = pairs[i:i + batch_size]
            df = scraper.run([s for _, s in batch])
            if df.empty:
                self.log.warning(f"Batch ADMET {i // batch_size + 1} tidak mengembalikan data.")
                continue
            if len(df) != len(batch):
                self.log.warning(
                    f"Batch ADMET {i // batch_size + 1}: jumlah baris hasil ({len(df)}) tidak cocok "
                    f"dengan jumlah senyawa terkirim ({len(batch)}), korespondensi posisional tidak "
                    f"bisa dipercaya, batch ini DILEWATI demi integritas data."
                )
                continue
            for (name, _), (_, row) in zip(batch, df.iterrows()):
                record = {"ligand": name}
                record.update(row.to_dict())
                rows.append(record)

        self.log.info(f"ADMET diperoleh untuk {len(rows)}/{len(pairs)} senyawa.")
        return rows


    def _prepare_receptors(self):
        entries = read_receptors(
            self.cfg.receptor_excel, pdb_col=self.cfg.receptor_pdb_col,
            cx_col=self.cfg.receptor_cx_col, cy_col=self.cfg.receptor_cy_col, cz_col=self.cfg.receptor_cz_col,
            sx_col=self.cfg.receptor_sx_col, sy_col=self.cfg.receptor_sy_col, sz_col=self.cfg.receptor_sz_col,
            logger=self.log,
        )

        targets: List[ReceptorDockingTarget] = []
        rmsd_context: Dict[str, Any] = {}

        for entry in tqdm(entries, desc="Preparasi reseptor", unit="reseptor", disable=not self.cfg.show_progress):
            try:
                fetched = fetch_pdb(entry.pdb_code, self.cfg.receptor_dir / "_pdb_cache", logger=self.log)
                grid_box, native = self._resolve_gridbox(entry, fetched)

                mol = self._receptor_preparer.load(fetched.pdb_path)
                rec_dir = self.cfg.receptor_dir / entry.unique_key
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

                targets.append(ReceptorDockingTarget(
                    key=entry.unique_key, pdb_code=entry.pdb_code,
                    receptor_pdbqt=docking_pdbqt, receptor_clean_pdb=clean_pdb, grid_box=grid_box,
                ))
                if native is not None:
                    rmsd_context[entry.unique_key] = {"native": native, "grid_box": grid_box,
                                                       "receptor_pdbqt": docking_pdbqt}
            except Exception as exc:
                self.failed_receptors.append(entry.pdb_code)
                self.log.error(f"Preparasi reseptor '{entry.pdb_code}' gagal: {exc}")

        self.log.info(f"Reseptor siap docking: {len(targets)}/{len(entries)}")
        return targets, rmsd_context

    def _resolve_gridbox(self, entry, fetched):
        if entry.has_gridbox_center:
            sx = entry.size_x or entry.uniform_size or self.cfg.default_box_size
            sy = entry.size_y or entry.uniform_size or self.cfg.default_box_size
            sz = entry.size_z or entry.uniform_size or self.cfg.default_box_size

            native = None
            if self.cfg.run_rmsd_validation:
                if fetched.native_ligands:
                    native = min(
                        fetched.native_ligands,
                        key=lambda lig: (lig.center_x - entry.center_x) ** 2
                        + (lig.center_y - entry.center_y) ** 2
                        + (lig.center_z - entry.center_z) ** 2,
                    )
                else:
                    self.log.warning(
                        f"Validasi RMSD diminta untuk '{entry.pdb_code}' tapi tidak ada ligan "
                        f"native terdeteksi di struktur ini, dilewati untuk reseptor ini."
                    )

            return GridBox.from_manual(entry.center_x, entry.center_y, entry.center_z, sx, sy, sz), native

        if self.cfg.interactive_gridbox:
            cx, cy, cz, sx, sy, sz, native = interactive_select_native_ligand(
                fetched, default_size=(self.cfg.default_box_size,) * 3,
            )
            return GridBox.from_manual(cx, cy, cz, sx, sy, sz, ref_label=native.label if native else None), native

        raise ValueError(
            f"Reseptor '{entry.pdb_code}' tidak punya gridbox eksplisit di Excel dan mode interaktif "
            f"dimatikan, tidak ada cara menentukan lokasi docking."
        )


    def _run_rmsd_validation(self, rmsd_context, targets, orchestrator, vina_runner) -> List[Dict[str, Any]]:
        validator = RedockingValidator(self.cfg.rmsd_threshold_good, self.cfg.rmsd_threshold_acceptable,
                                        logger=self.log)
        rows: List[Dict[str, Any]] = []

        for target in tqdm(targets, desc="Validasi RMSD redocking", unit="reseptor", disable=not self.cfg.show_progress):
            ctx = rmsd_context.get(target.key)
            if not ctx:
                continue
            native = ctx["native"]
            try:
                native_smiles = derive_native_smiles(
                    native.to_pdb_block(), native.resname, self.cfg.cache_dir / "ligand_templates", self.log,
                )

                safe_name = f"NATIVE_{sanitize_filename(native.label)}"
                native_prep = self._ligand_preparer.prepare(
                    safe_name, native_smiles, self.cfg.ligand_dir / safe_name,
                    force_field=self.cfg.force_field, generate_image=False,
                )

                redock_dir = self.cfg.docking_dir / target.key / "_rmsd_validation"
                poses = vina_runner.run(
                    receptor_pdbqt=target.receptor_pdbqt, ligand_pdbqt=native_prep.pdbqt_path,
                    output_pdbqt=redock_dir / "redock_out.pdbqt", log_file=redock_dir / "redock.log",
                    grid_box=target.grid_box, exhaustiveness=self.cfg.exhaustiveness,
                    num_modes=self.cfg.num_modes, energy_range=self.cfg.energy_range,
                )
                if not poses:
                    raise ValueError("Redocking tidak menghasilkan pose.")

                best_pose_mols = read_pdbqt(redock_dir / "redock_out.pdbqt", logger=self.log)
                if not best_pose_mols:
                    raise ValueError("Pose redocking tidak terbaca dari PDBQT.")

                result = validator.validate(native.to_pdb_block(), best_pose_mols[0], native.label)
                rows.append({
                    "receptor": target.key, "native_ligand": native.label,
                    "rmsd_angstrom": result.rmsd, "status": result.status,
                    "redock_affinity": poses[0]["affinity"],
                    "metode": result.method, "catatan": result.note,
                })
            except Exception as exc:
                self.log.warning(f"Validasi RMSD gagal untuk reseptor '{target.key}': {exc}")
                rows.append({"receptor": target.key, "native_ligand": native.label,
                              "rmsd_angstrom": None, "status": "gagal", "redock_affinity": None,
                              "metode": "-", "catatan": str(exc)})

        return rows


    def _merge_native_reference(self, rmsd_context, targets) -> None:
        """Merge pose kristalografi ASLI ligan native (bukan hasil docking) ke
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
                clean_receptor = Chem.MolFromPDBFile(str(target.receptor_clean_pdb), sanitize=True, removeHs=False)
                native_mol = Chem.MolFromPDBBlock(native.to_pdb_block(), sanitize=True, removeHs=False)
                if clean_receptor is None or native_mol is None:
                    continue
                out_path = self.cfg.complex_dir / target.key / f"NATIVE_{sanitize_filename(native.label)}_complex.pdb"
                merge_complex(clean_receptor, native_mol, out_path, ligand_name=native.label,
                              is_native=True, logger=self.log)
            except Exception as exc:
                self.log.warning(f"Merge referensi native gagal untuk reseptor '{key}': {exc}")

    def _merge_poses(self, docking_results, targets) -> None:
        """Merge pose docking ke kompleks reseptor bersih.

        ``self.cfg.merge_mode``:
            - ``"best"``: satu file per (ligan, reseptor), pose dari replikat
              dengan afinitas terbaik SECARA GLOBAL (bukan diasumsikan replikat 1).
            - ``"all"``: satu file per pose per replikat sukses, semua di-merge.
        """
        from rdkit import Chem

        target_by_key = {t.key: t for t in targets}

        if self.cfg.merge_mode == "best":
            best_by_pair: Dict[Any, Any] = {}
            for r in docking_results:
                if not r.success:
                    continue
                pair_key = (r.ligand_name, r.receptor_key)
                current = best_by_pair.get(pair_key)
                if current is None or r.best_affinity < current.best_affinity:
                    best_by_pair[pair_key] = r
            selected = list(best_by_pair.values())
        else:
            selected = [r for r in docking_results if r.success]

        for r in tqdm(selected, desc="Merge kompleks", unit="pose", disable=not self.cfg.show_progress):
            target = target_by_key.get(r.receptor_key)
            if target is None:
                continue
            try:
                clean_receptor = Chem.MolFromPDBFile(str(target.receptor_clean_pdb), sanitize=True, removeHs=False)
                pose_mols = read_pdbqt(r.output_pdbqt, logger=self.log)
                if clean_receptor is None or not pose_mols:
                    continue

                stem = sanitize_filename(r.ligand_name)
                if self.cfg.merge_mode == "best":
                    out_path = self.cfg.complex_dir / target.key / f"{stem}_complex.pdb"
                    merge_complex(clean_receptor, pose_mols[0], out_path, ligand_name=r.ligand_name, logger=self.log)
                else:
                    for mode_idx, pose_mol in enumerate(pose_mols, start=1):
                        out_path = (self.cfg.complex_dir / target.key /
                                    f"{stem}_rep{r.replicate:02d}_mode{mode_idx:02d}_complex.pdb")
                        merge_complex(clean_receptor, pose_mol, out_path, ligand_name=r.ligand_name, logger=self.log)
            except Exception as exc:
                self.log.warning(f"Merge gagal untuk '{r.ligand_name}'x'{r.receptor_key}' rep{r.replicate}: {exc}")


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
                "status": "siap" if safe_name in results else "gagal",
            })
        return rows

    def _generate_charts(self, replicate_stats, lipinski_rows, admet_rows) -> None:
        if not replicate_stats:
            return
        builder = ChartBuilder(self.cfg.analytics_dir, dpi=self.cfg.figure_dpi,
                               formats=self.cfg.figure_formats, logger=self.log)

        multi_receptor = len({r["receptor"] for r in replicate_stats}) > 1

        def _display_label(row) -> str:
            return f'{row["ligand"]} ({row["receptor"]})' if multi_receptor else row["ligand"]

        labeled_stats = [{**r, "_display_label": _display_label(r)} for r in replicate_stats]
        builder.bar_affinity(labeled_stats, ligand_key="_display_label", value_key="affinity_best")

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
            )

        if admet_rows:
            builder.radar_all_admet_categories(admet_rows, label_key="ligand")
            builder.admet_all_stacked_bars(admet_rows)

    def _descriptor_matrix(self, records, lipinski_rows, feature_cols):
        group_by_name = {_file_name(r): (r.group or "Tanpa Grup") for r in records}
        lip_by_name = {r["ligand"]: r for r in lipinski_rows}

        matrix, labels, groups = [], [], []
        for name, lip in lip_by_name.items():
            matrix.append([lip[c] for c in feature_cols])
            labels.append(name)
            groups.append(group_by_name.get(name, "Tanpa Grup"))
        return matrix, labels, groups

    def _run_pca(self, records, lipinski_rows, admet_rows) -> None:
        feature_cols = ["MW", "LogP", "HBD", "HBA"]
        matrix, labels, groups = self._descriptor_matrix(records, lipinski_rows, feature_cols)

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

    def _run_hca(self, records, lipinski_rows) -> None:
        feature_cols = ["MW", "LogP", "HBD", "HBA"]
        matrix, labels, groups = self._descriptor_matrix(records, lipinski_rows, feature_cols)

        try:
            hca = HierarchicalClustering(logger=self.log)
            result = hca.compute(matrix, labels, groups)
            hca.plot_dendrogram(result, self.cfg.analytics_dir / "hca_dendrogram.png",
                                dpi=self.cfg.figure_dpi, formats=self.cfg.figure_formats)
            self.log.info("HCA (dendrogram) berhasil dibuat.")
        except ValueError as exc:
            self.log.warning(f"HCA dilewati: {exc}")

    def _generate_heatmaps(self, replicate_stats, lipinski_rows) -> None:
        builder = HeatmapBuilder(self.cfg.analytics_dir, dpi=self.cfg.figure_dpi,
                                 formats=self.cfg.figure_formats, logger=self.log)
        if replicate_stats:
            builder.heatmap_affinity(replicate_stats)
        if lipinski_rows:
            builder.heatmap_properties(lipinski_rows, properties=["MW", "LogP", "HBD", "HBA"],
                                        filename="heatmap_fisikokimia.png",
                                        title="Heatmap Fisikokimia (Ligan x Parameter)")
            builder.heatmap_properties_clustered(
                lipinski_rows, properties=["MW", "LogP", "HBD", "HBA"],
                filename="heatmap_fisikokimia_klaster.png",
                title="Heatmap Fisikokimia Terklaster (Ligan x Parameter)",
            )
