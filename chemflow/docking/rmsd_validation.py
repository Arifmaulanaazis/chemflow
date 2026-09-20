"""
Validasi RMSD redocking. Mengukur seberapa dekat pose hasil docking Vina
terhadap posisi ligan native aslinya (kristalografi), sebagai validasi
standar bahwa parameter docking (gridbox, exhaustiveness, dll) sudah
menghasilkan pose yang masuk akal.

Kriteria literatur: RMSD < 2.0 A antara pose redocking dan ligan native
kristalografi umum dipakai sebagai kriteria "baik" pada validasi docking
(self-docking/redocking). Lihat Hevener et al. 2009, *J. Chem. Inf.
Model.* 49(2):444-460 (PMC2788795), salah satu rujukan yang sering dikutip
untuk kriteria ini. Variasi di literatur: sebagian studi memakai ambang
lebih longgar (2.0-3.0 A = "acceptable") atau lebih ketat (1.5 A). Kedua
ambang di sini (default 2.0 / 3.0 A) bisa dikonfigurasi via
``PipelineConfig.rmsd_threshold_good`` / ``rmsd_threshold_acceptable``.

RMSD dihitung terhadap koordinat kristalografi ligan native dan pada posisi
aslinya, tanpa superposisi (``rdMolAlign.CalcRMS``, memperhitungkan simetri
molekul). Pose Vina berada pada kerangka koordinat reseptor yang sama dengan
struktur kristal, sehingga pose yang bergeser di dalam kantong ikat ikut
terhitung sebagai selisih. Ini berbeda dari ``rmsd_lb``/``rmsd_ub`` yang
dilaporkan Vina, yang mengukur jarak antar pose docking dalam satu run, bukan
terhadap struktur referensi eksperimental.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np


@dataclass
class RmsdValidationResult:
    """Hasil satu validasi RMSD redocking."""
    ligand_label: str
    rmsd: Optional[float]
    status: str            # "good" | "acceptable" | "poor" | "gagal"
    method: str             # "CalcRMS" | "fallback_greedy" | "gagal"
    note: str = ""


class RedockingValidator:
    """Menghitung RMSD antara pose redocking terbaik dan ligan native asli."""

    def __init__(self, threshold_good: float = 2.0, threshold_acceptable: float = 3.0,
                 logger: Optional[logging.Logger] = None) -> None:
        self._good = threshold_good
        self._acceptable = threshold_acceptable
        self._log = logger or logging.getLogger(__name__)

    def validate(self, native_pdb_block: str, docked_pose_mol: Any, ligand_label: str) -> RmsdValidationResult:
        """Hitung RMSD (pada posisi asli, tanpa superposisi) antara pose docking terbaik dan koordinat kristalografi native.

        Args:
            native_pdb_block: blok PDB mentah residu ligan native (langsung
                dari koordinat kristalografi, tanpa minimisasi atau penambahan H;
                lihat ``io.pdb_fetcher.NativeLigand.to_pdb_block()``).
            docked_pose_mol: RDKit Mol pose terbaik hasil redocking (dari
                ``io.pdbqt_reader.read_pdbqt()``, mode 1).
            ligand_label: label untuk pelaporan (mis. "STU_A301").

        Returns:
            ``RmsdValidationResult`` dengan ``rmsd=None`` & ``status="gagal"``
            jika perhitungan gagal total (tidak pernah raise).
        """
        from rdkit import Chem

        try:
            native_mol = Chem.MolFromPDBBlock(native_pdb_block, sanitize=False, removeHs=True)
            if native_mol is None:
                return RmsdValidationResult(ligand_label, None, "gagal", "gagal",
                                             "Gagal memparse blok PDB ligan native.")
            try:
                Chem.SanitizeMol(native_mol, catchErrors=True)
            except Exception:
                pass

            pose_mol = Chem.RemoveHs(docked_pose_mol)
            native_mol = Chem.RemoveHs(native_mol)

            rmsd = self._try_calc_rms(pose_mol, native_mol)
            method = "CalcRMS"
            if rmsd is None:
                rmsd = self._fallback_greedy_rmsd(pose_mol, native_mol)
                method = "fallback_greedy"

            if rmsd is None:
                return RmsdValidationResult(ligand_label, None, "gagal", "gagal",
                                             "Kedua metode RMSD (CalcRMS dan pencocokan atom greedy) gagal, "
                                             "kemungkinan jumlah atau jenis atom pose dan native tidak cocok.")

            status = self._classify(rmsd)
            note = (f"RMSD pada posisi asli tanpa superposisi. Kriteria: <{self._good} A baik, "
                    f"{self._good}-{self._acceptable} A cukup, >{self._acceptable} A buruk (Hevener et al. 2009).")
            return RmsdValidationResult(ligand_label, round(rmsd, 3), status, method, note)

        except Exception as exc:
            self._log.warning(f"[RMSD] Validasi gagal untuk '{ligand_label}': {exc}")
            return RmsdValidationResult(ligand_label, None, "gagal", "gagal", str(exc))

    def _classify(self, rmsd: float) -> str:
        if rmsd < self._good:
            return "good"
        if rmsd < self._acceptable:
            return "acceptable"
        return "poor"

    def _try_calc_rms(self, probe: Any, ref: Any) -> Optional[float]:
        """Metode utama: ``rdMolAlign.CalcRMS`` (RMSD pada posisi asli, memperhitungkan
        simetri, atom-mapping otomatis lewat substructure match)."""
        try:
            from rdkit.Chem import rdMolAlign
            return float(rdMolAlign.CalcRMS(probe, ref))
        except Exception as exc:
            self._log.debug(f"[RMSD] CalcRMS gagal ({exc}), mencoba pencocokan atom greedy.")
            return None

    def _fallback_greedy_rmsd(self, probe: Any, ref: Any) -> Optional[float]:
        """Cadangan: pasangkan atom secara greedy menurut elemen dan jarak terdekat,
        lalu hitung RMSD pada posisi asli. Dipakai hanya bila ``CalcRMS`` gagal
        (mis. graf molekul sedikit berbeda karena perbedaan perception ikatan pada
        struktur kristalografi tanpa H).

        Pendekatan ini perkiraan: pemetaan atom tidak memperhatikan topologi, sehingga
        nilainya cenderung tidak lebih besar dari RMSD sebenarnya. Hasilnya dilaporkan
        dengan metode ``fallback_greedy`` supaya terlihat bukan hasil ``CalcRMS``.
        """
        if probe.GetNumConformers() == 0 or ref.GetNumConformers() == 0:
            return None

        probe_coords = probe.GetConformer(0).GetPositions()
        ref_coords = ref.GetConformer(0).GetPositions()
        probe_elems = [a.GetSymbol() for a in probe.GetAtoms()]
        ref_elems = [a.GetSymbol() for a in ref.GetAtoms()]

        if len(probe_elems) != len(ref_elems):
            return None
        if sorted(probe_elems) != sorted(ref_elems):
            return None

        pairs = self._greedy_match(probe_coords, probe_elems, ref_coords, ref_elems)
        if pairs is None:
            return None

        matched_probe = np.array([probe_coords[i] for i, _ in pairs])
        matched_ref = np.array([ref_coords[j] for _, j in pairs])
        diff = matched_probe - matched_ref
        return float(np.sqrt(np.mean(np.sum(diff ** 2, axis=1))))

    @staticmethod
    def _greedy_match(probe_coords: np.ndarray, probe_elems: list,
                       ref_coords: np.ndarray, ref_elems: list) -> Optional[list]:
        used_ref = set()
        pairs = []
        for i, elem in enumerate(probe_elems):
            candidates = [j for j, e in enumerate(ref_elems) if e == elem and j not in used_ref]
            if not candidates:
                return None
            dists = [np.linalg.norm(probe_coords[i] - ref_coords[j]) for j in candidates]
            best_j = candidates[int(np.argmin(dists))]
            used_ref.add(best_j)
            pairs.append((i, best_j))
        return pairs
