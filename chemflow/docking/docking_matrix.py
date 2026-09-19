"""
Orkestrasi matriks docking: ligan x reseptor x replikasi.

Mendukung multi-PDB secara alami. Setiap baris ``ReceptorDockingTarget``
(kunci unik, biasanya kode PDB atau ``KODE_R001`` untuk multi-situs) di-dock
terhadap setiap ligan yang berhasil disiapkan. Multi-replikasi menjalankan
Vina beberapa kali dengan seed berbeda per pasangan ligan-reseptor, lalu
hasilnya diagregasi (mean +- std afinitas) untuk menilai konsistensi.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from tqdm import tqdm

from chemflow.docking.grid_box import GridBox
from chemflow.docking.vina_runner import VinaRunner
from chemflow.utils.name_sanitizer import sanitize_filename


@dataclass
class ReceptorDockingTarget:
    """Satu target docking: reseptor + gridbox yang sudah dikonkretkan."""
    key: str                 # kunci unik, mis. "6LU7" atau "6LU7_R002" (multi-situs)
    pdb_code: str
    receptor_pdbqt: Path
    receptor_clean_pdb: Path  # untuk merge, TANPA H/muatan
    grid_box: GridBox


@dataclass
class DockingRunResult:
    """Hasil satu run Vina (satu pasangan ligan-reseptor-replikat)."""
    ligand_name: str
    receptor_key: str
    replicate: int
    seed: Optional[int]
    poses: List[Dict[str, Any]] = field(default_factory=list)
    output_pdbqt: Optional[Path] = None
    log_path: Optional[Path] = None
    error: Optional[str] = None

    @property
    def best_affinity(self) -> Optional[float]:
        return self.poses[0]["affinity"] if self.poses else None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.poses)


class DockingOrchestrator:
    """Menjalankan matriks docking penuh (ligand x receptor x replikat)."""

    def __init__(self, vina_runner: VinaRunner, logger: Optional[logging.Logger] = None) -> None:
        self._runner = vina_runner
        self._log = logger or logging.getLogger(__name__)

    def run_matrix(
        self,
        ligand_pdbqt_map: Dict[str, Path],
        targets: List[ReceptorDockingTarget],
        output_dir: Path,
        *,
        n_replicates: int = 1,
        exhaustiveness: int = 8,
        num_modes: int = 9,
        energy_range: float = 3.0,
        base_seed: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
        show_progress: bool = True,
    ) -> List[DockingRunResult]:
        """Jalankan docking untuk setiap kombinasi ligan x reseptor x replikat.

        Args:
            ligand_pdbqt_map: pemetaan nama ligan -> path .pdbqt siap docking.
            targets: daftar target reseptor (multi-PDB / multi-situs).
            output_dir: direktori dasar keluaran docking.
            n_replicates: jumlah pengulangan run per pasangan (>=1).
            exhaustiveness, num_modes, energy_range: parameter Vina.
            base_seed: seed dasar; ``None`` = seed acak tiap replikat.
            extra_args: argumen CLI Vina tambahan bebas.
            show_progress: tampilkan progress bar (tqdm) di terminal.

        Returns:
            Daftar ``DockingRunResult``. Satu run yang gagal TIDAK
            menghentikan run lain (error dicatat di ``.error``, matriks lanjut).
        """
        results: List[DockingRunResult] = []
        tasks = [
            (target, ligand_name, ligand_pdbqt, rep)
            for target in targets
            for ligand_name, ligand_pdbqt in ligand_pdbqt_map.items()
            for rep in range(1, n_replicates + 1)
        ]
        total = len(tasks)

        for done, (target, ligand_name, ligand_pdbqt, rep) in enumerate(
            tqdm(tasks, desc="Docking", unit="run", disable=not show_progress), start=1
        ):
            seed = self._resolve_seed(base_seed, rep)
            self._log.info(
                f"[{done}/{total}] Docking '{ligand_name}' -> '{target.key}' (replikat {rep}/{n_replicates})"
            )

            pair_dir = output_dir / target.key / sanitize_filename(ligand_name)
            pair_dir.mkdir(parents=True, exist_ok=True)
            out_pdbqt = pair_dir / f"rep{rep:02d}_out.pdbqt"
            log_path = pair_dir / f"rep{rep:02d}.log"

            try:
                poses = self._runner.run(
                    receptor_pdbqt=target.receptor_pdbqt,
                    ligand_pdbqt=ligand_pdbqt,
                    output_pdbqt=out_pdbqt,
                    log_file=log_path,
                    grid_box=target.grid_box,
                    exhaustiveness=exhaustiveness,
                    num_modes=num_modes,
                    energy_range=energy_range,
                    seed=seed,
                    extra_args=extra_args,
                )
                results.append(DockingRunResult(
                    ligand_name=ligand_name, receptor_key=target.key, replicate=rep, seed=seed,
                    poses=poses, output_pdbqt=out_pdbqt, log_path=log_path,
                ))
            except Exception as exc:
                self._log.error(f"Docking gagal '{ligand_name}'x'{target.key}' rep{rep}: {exc}")
                results.append(DockingRunResult(
                    ligand_name=ligand_name, receptor_key=target.key, replicate=rep, seed=seed,
                    error=str(exc),
                ))

        return results

    @staticmethod
    def _resolve_seed(base_seed: Optional[int], replicate: int) -> Optional[int]:
        if base_seed is None:
            return random.randint(1, 2_000_000_000)
        return base_seed + replicate - 1


def compute_replicate_stats(results: List[DockingRunResult]) -> List[Dict[str, Any]]:
    """Agregasi mean +- std afinitas antar replikat per pasangan ligan-reseptor.

    Args:
        results: hasil ``DockingOrchestrator.run_matrix()``.

    Returns:
        Satu baris per pasangan (ligand, receptor) unik: jumlah replikat
        sukses, afinitas rata-rata, std deviasi (0.0 jika hanya 1 replikat),
        afinitas terbaik keseluruhan.
    """
    groups: Dict[tuple, List[float]] = {}
    for r in results:
        if r.success:
            groups.setdefault((r.ligand_name, r.receptor_key), []).append(r.best_affinity)

    rows: List[Dict[str, Any]] = []
    for (ligand, receptor), affinities in groups.items():
        arr = np.array(affinities)
        rows.append({
            "ligand": ligand,
            "receptor": receptor,
            "n_replicates_success": len(arr),
            "affinity_mean": round(float(arr.mean()), 3),
            "affinity_std": round(float(arr.std()), 3) if len(arr) > 1 else 0.0,
            "affinity_best": round(float(arr.min()), 3),
        })
    return rows
