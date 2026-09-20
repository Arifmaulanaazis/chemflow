"""
Runner AutoDock Vina. Jalankan satu docking reseptor-ligan.

Desain kunci: argumen ``--log`` sengaja tidak dipakai karena tidak
didukung Vina versi >1.1.2. Sebagai gantinya, seluruh output stdout
ditangkap secara streaming (``Popen`` + ``readline()``) dan disimpan
manual ke file log setelah proses selesai. Cara ini bekerja seragam di
semua versi Vina modern tanpa perlu tahu versi persisnya terlebih dahulu.

Parser tabel skor mencari baris separator
``-----+------------+----------+----------`` lalu membaca baris berikutnya
yang diawali angka. Berbasis pola teks, bukan posisi baris tetap, jadi
otomatis toleran ada/tidaknya opsi lain di output Vina.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from chemflow.docking.grid_box import GridBox
from chemflow.docking.vina_manager import VinaReleaseManager
from chemflow.utils.subprocess_stream import stream_process


class VinaRunner:
    """Menjalankan AutoDock Vina untuk satu pasang reseptor-ligan."""

    def __init__(self, vina_executable: Path, logger: Optional[logging.Logger] = None) -> None:
        self._exe = str(vina_executable)
        self._log = logger or logging.getLogger(__name__)

    def run(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        output_pdbqt: Path,
        log_file: Path,
        grid_box: GridBox,
        *,
        exhaustiveness: int = 8,
        num_modes: int = 9,
        energy_range: float = 3.0,
        seed: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
        on_output: Optional[Callable[[str], None]] = None,
        verbose: bool = False,
    ) -> List[Dict[str, Any]]:
        """Jalankan satu docking run Vina.

        Args:
            receptor_pdbqt: reseptor .pdbqt rigid (H polar + muatan Kollman).
            ligand_pdbqt: ligan .pdbqt (hasil ``LigandPreparer``).
            output_pdbqt: path keluaran multi-pose.
            log_file: path log manual (ditulis dari stdout tertangkap).
            grid_box: parameter gridbox (harus sudah dikonkretkan, non-auto).
            exhaustiveness, num_modes, energy_range: parameter pencarian Vina.
            seed: seed acak (untuk multi-replikasi dgn hasil berbeda per run).
            extra_args: argumen CLI tambahan bebas (custom flags Vina lain).
            on_output: callback per baris output (opsional, utk progress UI).
            verbose: cetak output Vina ke terminal secara real-time.

        Returns:
            Daftar pose: ``[{mode, affinity, rmsd_lb, rmsd_ub}, ...]``
            terurut sesuai output Vina (mode 1 = afinitas terbaik).

        Raises:
            RuntimeError: Vina keluar dengan kode error non-nol.
        """
        output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self._exe,
            "--receptor", str(receptor_pdbqt),
            "--ligand", str(ligand_pdbqt),
            "--out", str(output_pdbqt),
            "--exhaustiveness", str(exhaustiveness),
            "--num_modes", str(num_modes),
            "--energy_range", str(energy_range),
            *grid_box.vina_args(),
        ]
        if seed is not None:
            cmd.extend(["--seed", str(seed)])
        if extra_args:
            cmd.extend(extra_args)

        self._log.info(f"Perintah Vina: {' '.join(cmd)}")
        ret, lines = stream_process(cmd, on_line=on_output, echo=verbose)

        try:
            log_file.write_text("".join(lines), encoding="utf-8")
        except Exception as exc:
            self._log.warning(f"Gagal menulis log {log_file}: {exc}")

        if ret != 0:
            tail = "".join(lines[-30:])
            raise RuntimeError(
                f"Vina keluar dengan kode {ret} untuk ligan '{ligand_pdbqt.stem}'.\n"
                f"30 baris output terakhir:\n{tail}"
            )

        poses = self._parse_score_table(lines)
        if poses:
            self._log.info(f"Vina selesai: {len(poses)} pose, afinitas terbaik={poses[0]['affinity']} kcal/mol")
        else:
            self._log.warning("Vina selesai tapi tabel skor tidak terparse dari output.")
        return poses

    @staticmethod
    def _parse_score_table(lines: List[str]) -> List[Dict[str, Any]]:
        poses: List[Dict[str, Any]] = []
        parsing = False
        for raw in lines:
            line = raw.rstrip("\n")
            if "-----+" in line and "----------" in line:
                parsing = True
                continue
            if not parsing or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit():
                try:
                    pose = {"mode": int(parts[0]), "affinity": float(parts[1])}
                    if len(parts) >= 4:
                        pose["rmsd_lb"] = float(parts[2])
                        pose["rmsd_ub"] = float(parts[3])
                    poses.append(pose)
                except ValueError:
                    continue
        return poses


def resolve_vina_executable(
    manager: VinaReleaseManager,
    version: Optional[str] = None,
    explicit_path: Optional[Path] = None,
) -> Path:
    """Tentukan executable Vina yang dipakai.

    Resolusi tidak pernah bergantung pada PATH sistem: baik ``explicit_path``
    maupun hasil ``manager.resolve()`` selalu berupa path absolut siap
    dieksekusi langsung (dari cache lokal atau hasil auto-download).

    Args:
        manager: instance ``VinaReleaseManager``.
        version: versi spesifik yang diminta pengguna.
        explicit_path: override path manual (prioritas tertinggi).

    Returns:
        Path executable Vina siap pakai.
    """
    if explicit_path is not None:
        return explicit_path
    return manager.resolve(version=version)
