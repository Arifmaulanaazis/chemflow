"""
Pengambil file PDB dari RCSB + deteksi ligan native (untuk pusat gridbox
otomatis dan validasi RMSD redocking).

Residu HETATM yang sebenarnya bagian dari rantai polipeptida (asam amino
termodifikasi, mis. MSE) dikeluarkan dari daftar "kandidat ligan native"
lewat pengecekan struktural ``is_polymer_backbone_complete``, bukan
daftar nama hardcode, supaya konsisten dengan logika preparasi reseptor.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from chemflow.docking.grid_box import GridBox, parse_box_size
from chemflow.utils.residue_backbone import is_polymer_backbone_complete

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download/{pdb_code}.pdb"
_PDB_CODE = re.compile(r"[0-9A-Z]{4}")

# Residu yang jelas bukan kandidat ligan (pelarut, aditif kristalisasi, ion umum).
_SOLVENT_RESNAMES = {
    "HOH", "WAT", "DOD", "H2O", "EDO", "GOL", "DMS",
    "SO4", "PO4", "ACT", "ACE", "MES", "TRS", "EPE",
}


@dataclass
class NativeLigand:
    """Satu kandidat ligan native yang terdeteksi dari blok HETATM."""
    chain: str
    resname: str
    resnum: int
    atom_lines: List[str] = field(default_factory=list)  # baris HETATM asli (koordinat kristalografi)
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.resname}_{self.chain}{self.resnum}"

    @property
    def atom_count(self) -> int:
        return len(self.atom_lines)

    @property
    def extent(self) -> float:
        """Sisi bounding-box terpanjang ligan dalam Angstrom."""
        coords = [(float(l[30:38]), float(l[38:46]), float(l[46:54])) for l in self.atom_lines]
        if not coords:
            return 0.0
        return max(max(c[axis] for c in coords) - min(c[axis] for c in coords) for axis in range(3))

    def to_pdb_block(self) -> str:
        """Blok PDB minimal (ATOM/HETATM + END) untuk residu ini saja,
        dipakai sebagai referensi kristalografi pada validasi RMSD, tanpa
        modifikasi apa pun (tidak diminimisasi, tidak ditambah H)."""
        return "".join(self.atom_lines) + "END\n"


@dataclass
class FetchedReceptor:
    pdb_code: str
    pdb_path: Path
    native_ligands: List[NativeLigand] = field(default_factory=list)


def fetch_pdb(pdb_code: str, dest_dir: Path, logger: Optional[logging.Logger] = None) -> FetchedReceptor:
    """Unduh file PDB dari RCSB (cache berbasis keberadaan file) & parse ligan native.

    Args:
        pdb_code: kode PDB 4 karakter (tidak case-sensitive).
        dest_dir: direktori penyimpanan file .pdb.
        logger: logger opsional.

    Returns:
        ``FetchedReceptor`` berisi path file & daftar kandidat ligan native.

    Raises:
        RuntimeError: gagal mengunduh dari RCSB.
    """
    code = pdb_code.strip().upper()
    if not _PDB_CODE.fullmatch(code):
        raise RuntimeError(f"Kode PDB tidak valid: {pdb_code!r}. Kode terdiri dari 4 huruf atau angka.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    pdb_path = dest_dir / f"{code}.pdb"

    log = logger or logging.getLogger(__name__)
    if not pdb_path.exists():
        url = RCSB_DOWNLOAD_URL.format(pdb_code=code)
        log.info(f"Mengunduh {code} dari RCSB: {url}")
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Gagal mengunduh PDB {code}: {exc}") from exc
        pdb_path.write_bytes(resp.content)
        log.info(f"Tersimpan: {code}.pdb ({pdb_path.stat().st_size // 1024} KB)")
    else:
        log.info(f"Memakai cache: {code}.pdb")

    ligands = _parse_native_ligands(pdb_path)
    return FetchedReceptor(pdb_code=code, pdb_path=pdb_path, native_ligands=ligands)


def _parse_native_ligands(pdb_path: Path) -> List[NativeLigand]:
    """Kelompokkan baris HETATM per (chain, resname, resnum), buang pelarut
    & residu yang secara struktural bagian dari backbone protein."""
    groups: Dict[Tuple[str, str, int], List[str]] = {}
    atom_elements: Dict[Tuple[str, str, int], Dict[str, str]] = {}

    text = pdb_path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines(keepends=True):
        if not line.startswith("HETATM"):
            continue
        try:
            atom_name = line[12:16].strip().upper()
            resname = line[17:20].strip().upper()
            chain = line[21:22].strip() or "A"
            resnum = int(line[22:26].strip())
        except (ValueError, IndexError):
            continue

        if resname in _SOLVENT_RESNAMES or len(resname) <= 1:
            continue

        element = line[76:78].strip().upper() if len(line) >= 78 else ""
        if not element:
            element = atom_name[:1]

        key = (chain, resname, resnum)
        groups.setdefault(key, []).append(line)
        if atom_name:
            atom_elements.setdefault(key, {})[atom_name] = element

    ligands: List[NativeLigand] = []
    for key, lines in groups.items():
        chain, resname, resnum = key
        if is_polymer_backbone_complete(atom_elements.get(key, {})):
            continue
        coords = [(float(l[30:38]), float(l[38:46]), float(l[46:54])) for l in lines]
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        cz = sum(c[2] for c in coords) / len(coords)
        ligands.append(NativeLigand(
            chain=chain, resname=resname, resnum=resnum, atom_lines=lines,
            center_x=round(cx, 3), center_y=round(cy, 3), center_z=round(cz, 3),
        ))

    ligands.sort(key=lambda l: -l.atom_count)
    return ligands


def interactive_select_native_ligand(
    receptor: FetchedReceptor,
    default_size: Tuple[float, float, float] = (20.0, 20.0, 20.0),
    padding: float = 8.0,
) -> Tuple[float, float, float, float, float, float, Optional[NativeLigand]]:
    """Prompt TTY interaktif untuk memilih ligan native sebagai pusat gridbox.

    Dipanggil hanya ketika Excel reseptor tidak menyediakan koordinat
    gridbox eksplisit. Pilihan ini juga menentukan ligan mana yang dipakai
    untuk validasi RMSD redocking (jika diaktifkan).

    Ukuran default kotak diturunkan dari ligan native yang dipilih (kubus:
    ekstensi native + ``padding``, lihat ``GridBox.suggested_size``). ``default_size``
    hanya dipakai bila tak ada native (koordinat manual).

    Returns:
        ``(cx, cy, cz, sx, sy, sz, ligan_terpilih_atau_None)``.

    Raises:
        RuntimeError: dipanggil tanpa terminal interaktif (non-TTY).
    """
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Pemilihan gridbox interaktif diminta, tapi tidak ada terminal interaktif "
            "(stdin non-TTY). Sediakan koordinat gridbox eksplisit di Excel reseptor."
        )
    ligands = receptor.native_ligands

    print(f"\n  === Pemilihan Gridbox: Reseptor {receptor.pdb_code} ===")
    if not ligands:
        print(f"  [!] Tidak ada ligan native terdeteksi di {receptor.pdb_code}.pdb")
        return _prompt_manual(default_size)

    header = (f"{'No':>3}  {'Chain':>5}  {'Residu':>8}  {'ResNum':>6}  {'Atom':>5}  "
              f"{'X':>9}  {'Y':>9}  {'Z':>9}  {'Kotak':>6}")
    print(f"  {header}\n  {'-' * len(header)}")
    for i, lig in enumerate(ligands, start=1):
        print(f"  {i:>3}  {lig.chain:>5}  {lig.resname:>8}  {lig.resnum:>6}  "
              f"{lig.atom_count:>5}  {lig.center_x:>9.3f}  {lig.center_y:>9.3f}  {lig.center_z:>9.3f}  "
              f"{GridBox.suggested_size(lig.extent, padding):>6.0f}")
    print(f"  {'m':>3}  -> masukkan koordinat manual")

    while True:
        raw = input(f"  Pilih nomor ligan [1-{len(ligands)} / m]: ").strip()
        if raw.lower() == "m":
            return _prompt_manual(default_size)
        try:
            idx = int(raw)
        except ValueError:
            print("  [!] Masukan tidak valid.")
            continue
        if 1 <= idx <= len(ligands):
            lig = ligands[idx - 1]
            print(f"  [OK] Dipilih: {lig.label} -> pusat ({lig.center_x}, {lig.center_y}, {lig.center_z})")
            side = GridBox.suggested_size(lig.extent, padding)
            ans = input(
                f"       Pakai ukuran {side:g} A (ekstensi native {lig.extent:.1f} A + padding {padding:g} A)? [Y/n]: "
            ).strip().lower()
            size = (side, side, side)
            if ans in ("n", "no"):
                size = _prompt_size(size)
            return lig.center_x, lig.center_y, lig.center_z, *size, lig
        print(f"  [!] Masukkan angka 1-{len(ligands)} atau 'm'.")


def _prompt_manual(default_size: Tuple[float, float, float]):
    cx = _prompt_float("  Center X: ")
    cy = _prompt_float("  Center Y: ")
    cz = _prompt_float("  Center Z: ")
    sx, sy, sz = default_size
    ans = input(f"  Pakai ukuran default {sx:g}x{sy:g}x{sz:g} A? [Y/n]: ").strip().lower()
    if ans in ("n", "no"):
        sx, sy, sz = _prompt_size(default_size)
    return cx, cy, cz, sx, sy, sz, None


def _prompt_size(default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Minta ukuran kotak: satu angka (kubus) atau tiga angka x y z; Enter memakai ``default``."""
    while True:
        size = parse_box_size(input("  Ukuran x y z dalam A (satu angka untuk kubus, Enter = default): "), default[0])
        if size is not None:
            return size
        print("  [!] Masukkan satu atau tiga angka positif.")


def _prompt_float(prompt: str) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("  [!] Masukkan angka yang valid.")
