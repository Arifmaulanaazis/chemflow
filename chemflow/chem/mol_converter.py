"""
Konversi molekul RDKit -> PDB -> PDBQT lewat OpenBabel CLI (``obabel``).

Beberapa kuirk penting yang membuat pemanggilan langsung ``subprocess.run``
naif gagal di Windows (semua ditangani di sini):
  - Format inference OpenBabel dari ekstensi file GAGAL DIAM-DIAM di Windows
    jika path output mengandung spasi -> selalu deklarasikan ``-i``/``-o``
    eksplisit, jangan andalkan ekstensi.
  - Flag ``-O<path>`` HARUS digabung tanpa spasi dengan path-nya (kuirk CLI
    OpenBabel, bukan typo).
  - OpenBabel dijalankan dengan ``cwd`` di direktori binary-nya sendiri pada
    beberapa instalasi portable -> semua path harus di-absolutkan dulu.
  - OpenBabel bisa exit code 0 walau gagal diam-diam (mis. output kosong)
    -> exit code SAJA tidak cukup, ukuran file output ikut divalidasi.
  - Reseptor rigid (``-xr``) kadang tetap ditulisi baris
    ROOT/ENDROOT/BRANCH/ENDBRANCH/TORSDOF oleh OpenBabel -> Vina menolak
    file semacam itu untuk reseptor, jadi baris-baris itu disaring manual.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from chemflow.utils.subprocess_stream import run_capture

_BANNED_RECEPTOR_TAGS = ("ROOT", "ENDROOT", "BRANCH", "ENDBRANCH", "TORSDOF")


def resolve_openbabel_executable(override: Optional[Path] = None) -> str:
    """Cari executable ``obabel``, hanya lewat PATH (sesuai asumsi bahwa
    OpenBabel sudah diinstal & ditambahkan ke PATH oleh pengguna), kecuali
    ``override`` diberikan secara eksplisit.

    Args:
        override: path eksplisit ke executable obabel (opsional).

    Returns:
        Path absolut ke executable.

    Raises:
        FileNotFoundError: obabel tidak ditemukan di PATH maupun override.
    """
    if override is not None:
        if Path(override).exists():
            return str(override)
        raise FileNotFoundError(f"OpenBabel tidak ditemukan di path yang diberikan: {override}")

    exe = shutil.which("obabel") or shutil.which("obabel.exe")
    if exe:
        return exe

    raise FileNotFoundError(
        "Executable 'obabel' tidak ditemukan di PATH. Install OpenBabel "
        "(https://openbabel.org) dan pastikan folder binary-nya ada di PATH sistem, "
        "atau tentukan lokasinya lewat --openbabel-path."
    )


class OpenBabelConverter:
    """Pembungkus pemanggilan OpenBabel CLI untuk konversi PDB <-> PDBQT."""

    def __init__(self, openbabel_path: Optional[Path] = None,
                 logger: Optional[logging.Logger] = None) -> None:
        self._obabel = resolve_openbabel_executable(openbabel_path)
        self._log = logger or logging.getLogger(__name__)

    def mol_to_pdb(self, mol: Any, output_pdb: Path) -> Path:
        """Tulis RDKit Mol ke file PDB dengan satu conformer.

        Args:
            mol: RDKit ``Mol`` (harus sudah punya conformer 3D).
            output_pdb: path tujuan.

        Returns:
            Path file .pdb yang ditulis.

        Raises:
            ValueError: RDKit gagal menghasilkan blok PDB (mis. tanpa conformer).
        """
        from rdkit import Chem  # type: ignore

        output_pdb.parent.mkdir(parents=True, exist_ok=True)
        m = mol
        if m.GetNumConformers() == 0:
            raise ValueError("Molekul tidak punya conformer 3D. Embed/minimisasi dulu sebelum konversi PDB.")

        try:
            Chem.MolToPDBFile(m, str(output_pdb))
        except Exception as exc:
            block = Chem.MolToPDBBlock(m) or ""
            if not block.strip():
                raise ValueError("RDKit gagal menulis blok PDB untuk molekul ini.") from exc
            output_pdb.write_text(block, encoding="utf-8")

        self._log.debug(f"PDB ditulis: {output_pdb.name}")
        return output_pdb

    def pdb_to_pdbqt(self, pdb_path: Path, output_pdbqt: Path, is_receptor: bool) -> Path:
        """Konversi file PDB -> PDBQT lewat OpenBabel.

        Args:
            pdb_path: file .pdb input.
            output_pdbqt: path .pdbqt output.
            is_receptor: True -> tambahkan ``-xr`` (reseptor rigid, tanpa
                pohon torsi). False -> ``-h`` (ligan, OpenBabel menghitung
                muatan Gasteiger & membangun pohon torsi sendiri, wajib
                untuk ligan karena tanpanya OpenBabel menghasilkan file kosong).

        Returns:
            Path file .pdbqt yang ditulis.

        Raises:
            ValueError: OpenBabel gagal atau menghasilkan output kosong.
        """
        output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
        ob_dir = Path(self._obabel).parent

        pdb_abs = pdb_path.absolute()
        out_abs = output_pdbqt.absolute()

        cmd = [self._obabel, "-i", "pdb", str(pdb_abs), "-o", "pdbqt", f"-O{out_abs}"]
        cmd.append("-xr" if is_receptor else "-h")

        self._log.debug(f"obabel: {' '.join(str(c) for c in cmd)}")
        result = run_capture(cmd, cwd=ob_dir)

        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip()
            raise ValueError(f"Konversi OpenBabel gagal (exit {result.returncode}): {msg}")

        if not output_pdbqt.exists() or output_pdbqt.stat().st_size == 0:
            self._log.error(f"Perintah: {' '.join(str(c) for c in cmd)}")
            self._log.error(f"STDOUT: {result.stdout}")
            self._log.error(f"STDERR: {result.stderr}")
            raise ValueError(
                f"OpenBabel menghasilkan output kosong untuk {pdb_path.name} "
                f"(exit code 0 tapi file kosong/tidak ada, indikasi kegagalan diam-diam)."
            )

        if is_receptor:
            self._strip_torsion_tags(output_pdbqt)

        self._log.debug(f"PDBQT ditulis: {output_pdbqt.name}")
        return output_pdbqt

    def mol_to_pdbqt(self, mol: Any, output_pdbqt: Path, is_receptor: bool) -> Path:
        """Ringkasan: RDKit Mol -> PDB sementara -> PDBQT dalam satu panggilan."""
        pdb_tmp = output_pdbqt.with_suffix(".tmp.pdb")
        try:
            self.mol_to_pdb(mol, pdb_tmp)
            return self.pdb_to_pdbqt(pdb_tmp, output_pdbqt, is_receptor=is_receptor)
        finally:
            pdb_tmp.unlink(missing_ok=True)

    @staticmethod
    def _strip_torsion_tags(pdbqt_path: Path) -> None:
        """Hapus baris ROOT/ENDROOT/BRANCH/ENDBRANCH/TORSDOF (Vina menolak
        file reseptor yang masih mengandung tag pohon-torsi ini)."""
        text = pdbqt_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines(keepends=True)
        if any(line.startswith(_BANNED_RECEPTOR_TAGS) for line in lines):
            clean = [ln for ln in lines if not ln.startswith(_BANNED_RECEPTOR_TAGS)]
            pdbqt_path.write_text("".join(clean), encoding="utf-8")
