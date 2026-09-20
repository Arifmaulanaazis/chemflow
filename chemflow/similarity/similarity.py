"""
Analisis similaritas interaksi ligan-reseptor terhadap ligan native/referensi.

Perhitungan mengikuti Pratama et al. (2021), "Introducing a two-dimensional
graph of docking score difference vs. similarity of ligand-receptor
interactions", Indonesian Journal of Biotechnology 26(1):54-60,
DOI 10.22146/ijbiotech.62194, Persamaan 2:

    %similarity = (0.5 * (nAAtest / nAAref) + 0.5 * (intAAtest / intAAref)) * 100%

- nAAtest/nAAref: rasio jumlah residu asam amino yang berinteraksi dengan
  ligan uji DAN juga berinteraksi dengan ligan referensi, dibagi total
  residu yang berinteraksi dengan ligan referensi (identitas residu saja,
  posisi+nama, tanpa mempedulikan tipe interaksi).
- intAAtest/intAAref: rasio jumlah pasangan (residu, tipe interaksi) yang
  sama-sama muncul di ligan uji dan referensi, dibagi total pasangan
  (residu, tipe interaksi) pada ligan referensi.

Input berupa daftar ``ProteinLigandContact`` (lihat ``biovia_reader.py``),
sudah disaring hanya kontak protein-ligan murni.

Modul ini juga menyediakan ``SimilarityAnalyzer``, orkestrator yang men-scan
folder hasil ``chemflow run`` (struktur ``complexes/<kunci>/*.pdb`` +
sidecar ``.json``) dan mencocokkannya dengan file interaksi BIOVIA yang
dibuat manual oleh pengguna, lalu mengekspor hasilnya ke Excel.

Analisis ini opsional (default tidak berjalan sebagai bagian ``run``) dan
bisa di-rerun kapan saja pada folder output yang sudah ada, karena file
interaksi BIOVIA memang baru dibuat pengguna setelah proses docking selesai.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from chemflow.similarity.biovia_reader import ProteinLigandContact, filter_protein_ligand, read_biovia_interactions


@dataclass
class SimilarityResult:
    """Hasil similaritas satu pasangan (ligan uji, ligan referensi native)."""
    receptor_key: str
    ligand_name: str
    reference_name: str
    n_aa_test: int
    n_aa_ref: int
    aa_similarity_pct: float
    int_aa_test: int
    int_aa_ref: int
    type_similarity_pct: float
    overall_similarity_pct: float
    matched_residues: List[str] = field(default_factory=list)
    matched_interactions: List[str] = field(default_factory=list)
    test_residues: List[str] = field(default_factory=list)
    reference_residues: List[str] = field(default_factory=list)
    affinity_test: Optional[float] = None
    affinity_ref: Optional[float] = None

    @property
    def delta_g(self) -> Optional[float]:
        """Selisih afinitas ligan uji terhadap referensi (kcal/mol); negatif berarti lebih kuat."""
        if self.affinity_test is None or self.affinity_ref is None:
            return None
        return round(self.affinity_test - self.affinity_ref, 3)


def compute_similarity(
    test_contacts: List[ProteinLigandContact],
    ref_contacts: List[ProteinLigandContact],
    *,
    ligand_name: str = "",
    reference_name: str = "",
    receptor_key: str = "",
    affinity_test: Optional[float] = None,
    affinity_ref: Optional[float] = None,
) -> SimilarityResult:
    """Hitung similaritas interaksi ligan uji vs ligan referensi (Eq. 2).

    Args:
        test_contacts: kontak protein-ligan ligan uji (hasil ``filter_protein_ligand``).
        ref_contacts: kontak protein-ligan ligan referensi native.
        ligand_name, reference_name, receptor_key: label untuk pelaporan.
        affinity_test, affinity_ref: afinitas docking (kcal/mol) ligan uji dan
            referensi, opsional, dipakai untuk selisih ΔG dan grafik similaritas vs ΔG.

    Returns:
        ``SimilarityResult`` lengkap dengan breakdown residu/interaksi yang cocok.

    Raises:
        ValueError: ligan referensi tidak punya kontak protein-ligan sama
            sekali (pembagi nol, similaritas tidak bermakna).
    """
    ref_residues = {c.residue_key for c in ref_contacts}
    if not ref_residues:
        raise ValueError(
            f"Ligan referensi '{reference_name}' tidak punya interaksi protein-ligan apa pun "
            f"(setelah menyaring intra-ligand/intra-protein), similaritas tidak bisa dihitung."
        )

    test_residues = {c.residue_key for c in test_contacts}
    ref_interactions = {(c.residue_key, c.interaction_type) for c in ref_contacts}
    test_interactions = {(c.residue_key, c.interaction_type) for c in test_contacts}

    matched_residue_keys = test_residues & ref_residues
    matched_interaction_keys = test_interactions & ref_interactions

    n_aa_test = len(matched_residue_keys)
    n_aa_ref = len(ref_residues)
    int_aa_test = len(matched_interaction_keys)
    int_aa_ref = len(ref_interactions)

    aa_pct = (n_aa_test / n_aa_ref) * 100.0
    type_pct = (int_aa_test / int_aa_ref) * 100.0 if int_aa_ref else 0.0
    overall_pct = 0.5 * aa_pct + 0.5 * type_pct

    residue_label = {c.residue_key: c.residue_label for c in ref_contacts}
    residue_label.update({c.residue_key: c.residue_label for c in test_contacts})

    return SimilarityResult(
        receptor_key=receptor_key, ligand_name=ligand_name, reference_name=reference_name,
        n_aa_test=n_aa_test, n_aa_ref=n_aa_ref, aa_similarity_pct=round(aa_pct, 2),
        int_aa_test=int_aa_test, int_aa_ref=int_aa_ref, type_similarity_pct=round(type_pct, 2),
        overall_similarity_pct=round(overall_pct, 2),
        matched_residues=sorted((residue_label[k] for k in matched_residue_keys), key=_residue_sort_key),
        matched_interactions=sorted(f"{residue_label[k]} ({t})" for k, t in matched_interaction_keys),
        test_residues=sorted((residue_label[k] for k in test_residues), key=_residue_sort_key),
        reference_residues=sorted((residue_label[k] for k in ref_residues), key=_residue_sort_key),
        affinity_test=affinity_test, affinity_ref=affinity_ref,
    )


def _residue_sort_key(label: str) -> int:
    try:
        return int(label.split("-")[0])
    except ValueError:
        return 0


class SimilarityAnalyzer:
    """Orkestrasi similaritas interaksi untuk seluruh folder output ``chemflow run``."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger(__name__)

    def analyze_output_dir(
        self,
        output_dir: "str | Path",
        interactions_dir: Optional["str | Path"] = None,
        interaction_suffix: str = "_interaksi.xlsx",
    ) -> List[SimilarityResult]:
        """Scan ``<output_dir>/complexes/`` dan hitung similaritas tiap ligan uji vs referensi native.

        Konvensi penamaan file interaksi (dibuat manual oleh pengguna dari
        export BIOVIA Discovery Studio): untuk setiap file kompleks
        ``complexes/<kunci>/<basis>.pdb``, file interaksinya harus ada di
        ``<interactions_dir>/<kunci>/<basis><interaction_suffix>``
        (default ``interactions_dir`` = ``<output_dir>/interaksi``, default
        ``interaction_suffix`` = ``"_interaksi.xlsx"``). Struktur folder
        ``<interactions_dir>`` membayangkan struktur ``complexes/`` persis.

        Reseptor tanpa kompleks referensi native (``is_native: true`` di
        sidecar JSON, dihasilkan otomatis oleh run yang mendeteksi ligan native,
        default ``include_native=True``)
        dilewati dengan warning, karena tidak ada baseline pembanding.
        Ligan uji yang file interaksinya belum dibuat/tidak ditemukan
        dilewati dengan warning (bukan fatal), sehingga bisa di-rerun
        bertahap saat pengguna menambah file interaksi satu per satu.

        Args:
            output_dir: folder output hasil ``chemflow run`` (berisi ``complexes/``).
            interactions_dir: folder interaksi BIOVIA manual (default: ``<output_dir>/interaksi``).
            interaction_suffix: akhiran nama file interaksi per kompleks.

        Returns:
            Daftar ``SimilarityResult``, satu per (ligan uji, reseptor) yang berhasil dihitung.

        Raises:
            FileNotFoundError: ``<output_dir>/complexes/`` tidak ada (belum pernah ``chemflow run``).
        """
        output_dir = Path(output_dir)
        complex_dir = output_dir / "complexes"
        if not complex_dir.exists():
            raise FileNotFoundError(
                f"Folder kompleks tidak ditemukan: {complex_dir}. Jalankan 'chemflow run' dulu "
                f"sebelum analisis similaritas."
            )

        interactions_dir = Path(interactions_dir) if interactions_dir else output_dir / "interaksi"

        test_affinity, reference_affinity = self._load_affinities(output_dir)

        results: List[SimilarityResult] = []
        for receptor_dir in sorted(p for p in complex_dir.iterdir() if p.is_dir()):
            results.extend(self._analyze_receptor(receptor_dir, interactions_dir, interaction_suffix,
                                                  test_affinity, reference_affinity))

        return results

    def _load_affinities(self, output_dir: Path):
        """Afinitas docking dari ``hasil_chemflow.xlsx`` (jika ada) untuk selisih ΔG.

        Returns:
            (afinitas ligan uji per ``(ligan, reseptor)``, afinitas redocking
            ligan native per reseptor); keduanya kosong jika file/sheet tak tersedia.
        """
        import pandas as pd

        workbook = output_dir / "hasil_chemflow.xlsx"
        test_affinity: Dict[Any, float] = {}
        reference_affinity: Dict[str, float] = {}
        if not workbook.exists():
            self._log.info("hasil_chemflow.xlsx tidak ada di folder output, selisih delta G tidak dihitung.")
            return test_affinity, reference_affinity

        native_affinity: Dict[str, float] = {}
        try:
            stats = pd.read_excel(workbook, sheet_name="Statistik Replikasi")
            for _, row in stats.iterrows():
                receptor, value = str(row["receptor"]), float(row["affinity_best"])
                test_affinity[(str(row["ligand"]), receptor)] = value
                if str(row.get("group", "")) == "Native":     # ligan native yang di-dock ulang bersama ligan uji
                    native_affinity[receptor] = min(value, native_affinity.get(receptor, value))
        except (ValueError, KeyError, OSError):
            self._log.info("Sheet 'Statistik Replikasi' tidak tersedia, selisih delta G tidak dihitung.")

        try:
            rmsd = pd.read_excel(workbook, sheet_name="Validasi RMSD")
            for _, row in rmsd.iterrows():
                if pd.notna(row.get("redock_affinity")):
                    reference_affinity[str(row["receptor"])] = float(row["redock_affinity"])
        except (ValueError, KeyError, OSError):
            self._log.info("Sheet 'Validasi RMSD' tidak ada, referensi ΔG diambil dari docking ligan native.")

        # Tanpa --run-rmsd-validation tidak ada sheet RMSD, tetapi native tetap di-dock: pakai ΔG-nya.
        for receptor, value in native_affinity.items():
            reference_affinity.setdefault(receptor, value)
        if not reference_affinity:
            self._log.info("Afinitas ligan native tidak tersedia, selisih delta G tidak dihitung.")

        return test_affinity, reference_affinity

    def _analyze_receptor(self, receptor_dir: Path, interactions_dir: Path, suffix: str,
                          test_affinity: Optional[Dict[Any, float]] = None,
                          reference_affinity: Optional[Dict[str, float]] = None) -> List[SimilarityResult]:
        test_affinity = test_affinity or {}
        reference_affinity = reference_affinity or {}
        receptor_key = receptor_dir.name
        complex_pdbs = sorted(receptor_dir.glob("*_complex.pdb"))
        if not complex_pdbs:
            return []

        native_pdb, native_meta = None, None
        for pdb_path in complex_pdbs:
            meta = self._load_metadata(pdb_path)
            if meta and meta.get("is_native"):
                native_pdb, native_meta = pdb_path, meta
                break

        if native_pdb is None:
            self._log.warning(
                f"Reseptor '{receptor_key}': tidak ada kompleks referensi native (jalankan pipeline dengan "
                f"tanpa --no-native, dan pastikan struktur PDB-nya punya ligan native di dekat pusat kotak). "
                f"Similaritas dilewati untuk reseptor ini."
            )
            return []

        ref_interaction_path = self._expected_interaction_path(interactions_dir, receptor_key, native_pdb, suffix)
        if not ref_interaction_path.exists():
            self._log.warning(
                f"Reseptor '{receptor_key}': file interaksi referensi native tidak ditemukan, diharapkan di "
                f"'{ref_interaction_path}'. Buat file itu dari export BIOVIA Discovery Studio untuk kompleks "
                f"'{native_pdb.name}'. Reseptor ini dilewati untuk saat ini (bisa di-rerun setelah dibuat)."
            )
            return []

        try:
            ref_contacts = self._load_contacts(ref_interaction_path, native_meta["ligand_chain"])
        except (ValueError, FileNotFoundError) as exc:
            self._log.warning(f"Gagal membaca interaksi referensi '{ref_interaction_path.name}': {exc}. "
                               f"Reseptor '{receptor_key}' dilewati.")
            return []

        results: List[SimilarityResult] = []
        for pdb_path in complex_pdbs:
            if pdb_path == native_pdb:
                continue
            meta = self._load_metadata(pdb_path)
            if meta is None:
                self._log.warning(f"Metadata sidecar tidak ditemukan untuk '{pdb_path.name}' (file .json hilang), dilewati.")
                continue

            interaction_path = self._expected_interaction_path(interactions_dir, receptor_key, pdb_path, suffix)
            if not interaction_path.exists():
                self._log.warning(
                    f"Ligan '{meta.get('ligand_name', pdb_path.stem)}' x reseptor '{receptor_key}': file interaksi "
                    f"tidak ditemukan, diharapkan di '{interaction_path}'. Dilewati untuk saat ini."
                )
                continue

            try:
                test_contacts = self._load_contacts(interaction_path, meta["ligand_chain"])
                ligand_name = meta.get("ligand_name", pdb_path.stem)
                result = compute_similarity(
                    test_contacts, ref_contacts, ligand_name=ligand_name,
                    reference_name=native_meta.get("ligand_name", native_pdb.stem), receptor_key=receptor_key,
                    affinity_test=test_affinity.get((ligand_name, receptor_key)),
                    affinity_ref=reference_affinity.get(receptor_key),
                )
                results.append(result)
            except (ValueError, FileNotFoundError) as exc:
                self._log.warning(f"Similaritas gagal untuk '{pdb_path.name}': {exc}")

        return results

    @staticmethod
    def _load_metadata(pdb_path: Path) -> Optional[Dict[str, Any]]:
        json_path = pdb_path.with_suffix(".json")
        if not json_path.exists():
            return None
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _expected_interaction_path(interactions_dir: Path, receptor_key: str, pdb_path: Path, suffix: str) -> Path:
        return interactions_dir / receptor_key / f"{pdb_path.stem}{suffix}"

    @staticmethod
    def _load_contacts(interaction_path: Path, ligand_chain: str) -> List[ProteinLigandContact]:
        interactions = read_biovia_interactions(interaction_path)
        return filter_protein_ligand(interactions, ligand_chain)


def export_similarity_results(results: List[SimilarityResult], output_path: "str | Path",
                               logger: Optional[logging.Logger] = None) -> Path:
    """Tulis daftar ``SimilarityResult`` ke satu file Excel.

    Args:
        results: hasil ``SimilarityAnalyzer.analyze_output_dir()``.
        output_path: path file .xlsx keluaran.
        logger: logger opsional.

    Returns:
        Path file Excel yang ditulis.
    """
    import pandas as pd

    from chemflow.utils.excel_utils import autofit_columns

    log = logger or logging.getLogger(__name__)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [{
        "receptor": r.receptor_key, "ligand": r.ligand_name, "reference_ligand": r.reference_name,
        "n_aa_test": r.n_aa_test, "n_aa_ref": r.n_aa_ref, "aa_similarity_pct": r.aa_similarity_pct,
        "int_aa_test": r.int_aa_test, "int_aa_ref": r.int_aa_ref, "type_similarity_pct": r.type_similarity_pct,
        "overall_similarity_pct": r.overall_similarity_pct,
        "affinity_test": r.affinity_test, "affinity_ref": r.affinity_ref, "delta_g": r.delta_g,
        "matched_residues": ", ".join(r.matched_residues),
        "matched_interactions": ", ".join(r.matched_interactions),
    } for r in results]

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "receptor", "ligand", "reference_ligand", "n_aa_test", "n_aa_ref", "aa_similarity_pct",
        "int_aa_test", "int_aa_ref", "type_similarity_pct", "overall_similarity_pct",
        "affinity_test", "affinity_ref", "delta_g", "matched_residues", "matched_interactions",
    ])
    df.to_excel(output_path, sheet_name="Similaritas Interaksi", index=False)
    autofit_columns(output_path)

    log.info(f"Hasil similaritas diekspor ke: {output_path} ({len(results)} baris)")
    return output_path
