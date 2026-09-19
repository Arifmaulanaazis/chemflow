"""
Penyusun Excel reseptor secara interaktif.

Pengguna memasukkan kode PDB dan memilih ligan native; pusat dan ukuran
kotak docking dihitung dari koordinat ligan itu. File hasilnya langsung
dipakai sebagai ``--receptors`` pada ``chemflow run``.
"""

from __future__ import annotations

import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

from openpyxl import Workbook
from openpyxl.styles import Alignment

from chemflow.docking.grid_box import GridBox
from chemflow.io.pdb_fetcher import FetchedReceptor, NativeLigand, fetch_pdb
from chemflow.utils.excel_utils import BODY_FONT, autofit_worksheet, style_header

PDB_CODE_PATTERN = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
MAX_BOX_SIZE = 30.0
MANUAL_BOX_SIZE = 20.0
DEFAULT_FILENAME = "reseptor.xlsx"
SHEET_NAME = "Reseptor"
COLUMNS = ("pdb_code", "center_x", "center_y", "center_z", "size_x", "size_y", "size_z", "native_ligand")

Ask = Callable[[str], str]
Say = Callable[[str], None]
Fetch = Callable[[str, Path], FetchedReceptor]
Choice = Union[str, List[int], None]


@dataclass(frozen=True)
class ReceptorConfigRow:
    """Satu baris Excel reseptor: satu situs docking pada satu struktur PDB."""
    pdb_code: str
    center: Tuple[float, float, float]
    size: Tuple[float, float, float]
    native_ligand: str


def suggest_box_size(ligand: NativeLigand) -> float:
    """Sisi kubus (Angstrom) yang memuat ligan beserta ruang gerak, dibulatkan ke atas, maksimum 30."""
    box = GridBox.cube_for_extent(ligand.center_x, ligand.center_y, ligand.center_z, ligand.extent)
    return float(min(math.ceil(box.size_x), MAX_BOX_SIZE))


def parse_pdb_codes(text: str) -> Tuple[List[str], List[str]]:
    """Pisahkan masukan menjadi kode PDB valid (huruf besar, tanpa duplikat) dan token tidak valid."""
    valid: List[str] = []
    invalid: List[str] = []
    for token in re.split(r"[\s,;]+", text.strip()):
        if not token:
            continue
        code = token.upper()
        if not PDB_CODE_PATTERN.match(code):
            invalid.append(token)
        elif code not in valid:
            valid.append(code)
    return valid, invalid


def parse_ligand_choice(text: str, count: int) -> Choice:
    """Tafsirkan pilihan ligan: ``"m"`` (manual), ``"s"`` (lewati), daftar nomor 1-based, atau ``None`` bila tidak valid."""
    raw = text.strip().lower()
    if raw in ("m", "s"):
        return raw
    tokens = [t for t in re.split(r"[\s,;]+", raw) if t]
    if not tokens or not all(t.isdigit() for t in tokens):
        return None
    numbers = list(dict.fromkeys(int(t) for t in tokens))
    if any(n < 1 or n > count for n in numbers):
        return None
    return numbers


def parse_box_size(text: str, default: float) -> Optional[Tuple[float, float, float]]:
    """Tafsirkan ukuran kotak: kosong memakai ``default``, satu angka untuk kubus, tiga angka untuk x y z."""
    tokens = text.split()
    if not tokens:
        return (default, default, default)
    try:
        values = [float(t.replace(",", ".")) for t in tokens]
    except ValueError:
        return None
    if len(values) == 1:
        values = values * 3
    if len(values) != 3 or any(not math.isfinite(v) or v <= 0 for v in values):
        return None
    return (values[0], values[1], values[2])


def write_receptor_config(rows: Sequence[ReceptorConfigRow], path: "str | Path") -> Path:
    """Tulis baris konfigurasi ke Excel dengan kolom yang dibaca ``io.excel_receptors``."""
    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    ws.append(list(COLUMNS))
    for row in rows:
        ws.append([row.pdb_code, *row.center, *row.size, row.native_ligand])

    style_header(ws)
    for cells in ws.iter_rows(min_row=2):
        for cell in cells:
            cell.font = BODY_FONT
            cell.alignment = Alignment(horizontal="left", vertical="center")
    autofit_worksheet(ws)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def run_receptor_config(ask: Ask = input, say: Say = print, fetch: Fetch = fetch_pdb) -> int:
    """Jalankan alur interaktif dan simpan Excel reseptor.

    Args:
        ask: fungsi pengambil masukan pengguna (default ``input``).
        say: fungsi penampil teks (default ``print``).
        fetch: pengunduh struktur PDB, mengembalikan ``FetchedReceptor``.

    Returns:
        ``0`` bila file tertulis, ``1`` bila tidak ada baris yang dihasilkan.
    """
    say("Penyusun Excel reseptor chemflow")
    say("Masukkan kode PDB, lalu pilih ligan native yang menjadi pusat kotak docking.")
    say("Koordinat pusat dan ukuran kotak terisi otomatis dari ligan yang dipilih.")

    rows = _collect_rows(ask, say, fetch)
    if not rows:
        say("\nTidak ada baris reseptor yang dihasilkan, file tidak ditulis.")
        return 1

    _print_summary(rows, say)
    path = _save_rows(rows, ask, say)
    say(f"\nTersimpan: {path.resolve()} ({len(rows)} baris)")
    say("Pakai file ini sebagai --receptors:")
    say(f'  python -m chemflow run --ligands ligan.xlsx --receptors "{path}"')
    return 0


def _collect_rows(ask: Ask, say: Say, fetch: Fetch) -> List[ReceptorConfigRow]:
    codes = _ask_pdb_codes(ask, say)
    rows: List[ReceptorConfigRow] = []
    with tempfile.TemporaryDirectory(prefix="chemflow_pdb_") as tmp:
        for index, code in enumerate(codes, start=1):
            say(f"\n[{index}/{len(codes)}] {code}: mengunduh struktur dari RCSB")
            try:
                receptor = fetch(code, Path(tmp))
            except RuntimeError as exc:
                say(f"{exc}\nReseptor {code} dilewati.")
                continue
            rows.extend(_rows_for_receptor(receptor, ask, say))
    return rows


def _ask_pdb_codes(ask: Ask, say: Say) -> List[str]:
    while True:
        codes, invalid = parse_pdb_codes(ask("\nKode PDB (pisahkan dengan spasi atau koma, contoh 6LU7 3PTB): "))
        if invalid:
            say(f"Kode tidak valid: {', '.join(invalid)}. Kode PDB terdiri dari 4 karakter dan diawali angka.")
            continue
        if not codes:
            say("Masukkan minimal satu kode PDB.")
            continue
        return codes


def _rows_for_receptor(receptor: FetchedReceptor, ask: Ask, say: Say) -> List[ReceptorConfigRow]:
    ligands = receptor.native_ligands
    _print_ligand_table(receptor.pdb_code, ligands, say)

    if ligands:
        prompt = "Pilih nomor ligan (beberapa nomor dipisah spasi), m untuk koordinat manual, s untuk melewati: "
    else:
        prompt = "Ketik m untuk koordinat manual atau s untuk melewati: "

    while True:
        choice = parse_ligand_choice(ask(prompt), len(ligands))
        if choice is not None:
            break
        say("Masukan tidak valid.")

    if choice == "s":
        say(f"Reseptor {receptor.pdb_code} dilewati.")
        return []
    if choice == "m":
        center = (_ask_float("Center X: ", ask, say), _ask_float("Center Y: ", ask, say),
                  _ask_float("Center Z: ", ask, say))
        size = _ask_box_size(MANUAL_BOX_SIZE, ask, say)
        return [ReceptorConfigRow(receptor.pdb_code, center, size, "manual")]

    rows: List[ReceptorConfigRow] = []
    for number in choice:
        ligand = ligands[number - 1]
        say(f"\nLigan {ligand.label}: pusat ({ligand.center_x:.3f}, {ligand.center_y:.3f}, {ligand.center_z:.3f}), "
            f"panjang {ligand.extent:.1f} Angstrom.")
        size = _ask_box_size(suggest_box_size(ligand), ask, say)
        rows.append(ReceptorConfigRow(
            receptor.pdb_code, (ligand.center_x, ligand.center_y, ligand.center_z), size, ligand.label,
        ))
    return rows


def _print_ligand_table(pdb_code: str, ligands: Sequence[NativeLigand], say: Say) -> None:
    if not ligands:
        say(f"Tidak ada ligan native terdeteksi pada {pdb_code}.")
        return
    say(f"Ligan native pada {pdb_code}:")
    say(f"{'No':>4}  {'Chain':>5}  {'Residu':>7}  {'Nomor':>6}  {'Atom':>5}  "
        f"{'Pusat X':>9}  {'Pusat Y':>9}  {'Pusat Z':>9}  {'Kotak':>6}")
    for number, ligand in enumerate(ligands, start=1):
        say(f"{number:>4}  {ligand.chain:>5}  {ligand.resname:>7}  {ligand.resnum:>6}  {ligand.atom_count:>5}  "
            f"{ligand.center_x:>9.3f}  {ligand.center_y:>9.3f}  {ligand.center_z:>9.3f}  "
            f"{suggest_box_size(ligand):>6.0f}")


def _ask_float(prompt: str, ask: Ask, say: Say) -> float:
    while True:
        try:
            value = float(ask(prompt).strip().replace(",", "."))
        except ValueError:
            say("Masukkan angka yang valid.")
            continue
        if math.isfinite(value):
            return value
        say("Masukkan angka yang valid.")


def _ask_box_size(default: float, ask: Ask, say: Say) -> Tuple[float, float, float]:
    while True:
        size = parse_box_size(
            ask(f"Ukuran kotak x y z dalam Angstrom, Enter untuk {default:g} (satu angka untuk kubus): "), default,
        )
        if size is not None:
            return size
        say("Masukkan satu atau tiga angka positif.")


def _print_summary(rows: Sequence[ReceptorConfigRow], say: Say) -> None:
    say("\nRingkasan:")
    say(f"{'pdb_code':<9} {'native_ligand':<14} {'center_x':>9} {'center_y':>9} {'center_z':>9} "
        f"{'size_x':>7} {'size_y':>7} {'size_z':>7}")
    for row in rows:
        say(f"{row.pdb_code:<9} {row.native_ligand:<14} {row.center[0]:>9.3f} {row.center[1]:>9.3f} "
            f"{row.center[2]:>9.3f} {row.size[0]:>7g} {row.size[1]:>7g} {row.size[2]:>7g}")


def _save_rows(rows: Sequence[ReceptorConfigRow], ask: Ask, say: Say) -> Path:
    while True:
        raw = ask(f"\nNama file keluaran [{DEFAULT_FILENAME}]: ").strip().strip('"')
        path = Path(raw or DEFAULT_FILENAME)
        if path.suffix.lower() != ".xlsx":
            path = Path(f"{path}.xlsx")
        if path.exists() and ask(f"{path} sudah ada. Timpa? [y/N]: ").strip().lower() not in ("y", "ya"):
            continue
        try:
            return write_receptor_config(rows, path)
        except OSError as exc:
            say(f"Gagal menulis {path}: {exc}")
