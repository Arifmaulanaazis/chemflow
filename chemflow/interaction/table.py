"""
Tabel Non-bond BIOVIA: teks TSV hasil salin (Ctrl+C) menjadi berkas Excel.

Teks yang disalin BIOVIA tidak memuat baris judul dan hanya berisi kolom yang
sedang tampil di tabel. Judulnya dibaca dari antarmuka; ``DEFAULT_HEADERS``
adalah urutan kolom bawaan Discovery Studio 2021 bila judul tidak terbaca.
Format yang dihasilkan dibaca ``chemflow.similarity.biovia_reader``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

DEFAULT_HEADERS: Tuple[str, ...] = (
    "Name", "Visible", "Color", "Parent", "Distance", "Category", "Types",
    "From", "From Chemistry", "To", "To Chemistry",
    "Angle XDA", "Angle DAY", "Angle DHA", "Angle HAY", "Angle Deviation", "Theta",
)
_NUMERIC_PREFIXES = ("Distance", "Angle", "Theta")
SHEET_NAME = "Non-bond"


@dataclass(frozen=True)
class NonbondTable:
    """Isi tabel Non-bond: judul kolom yang tampil dan teks TSV (kosong bila tanpa interaksi)."""
    headers: Tuple[str, ...]
    text: str

    @property
    def rows(self) -> List[List[str]]:
        return parse_rows(self.text)


def parse_rows(text: str) -> List[List[str]]:
    """Pisahkan teks TSV (LF atau CRLF) menjadi baris; baris kosong dibuang."""
    rows = []
    for line in text.splitlines():
        cells = line.split("\t")
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    return rows


def _cell_value(header: str, value: str):
    """Angka untuk kolom jarak dan sudut, teks apa adanya untuk kolom lain."""
    if header.startswith(_NUMERIC_PREFIXES) and value.strip():
        try:
            return float(value)
        except ValueError:
            return value
    return value


def write_interaction_xlsx(table: NonbondTable, path: "str | Path") -> int:
    """Tulis tabel ke Excel (satu sheet ``Non-bond``) dan kembalikan jumlah baris interaksi.

    Tabel tanpa interaksi tetap menghasilkan berkas berisi judul saja, supaya
    pemanggil bisa membedakannya dari kompleks yang belum diekspor.
    """
    from openpyxl import Workbook

    rows = table.rows
    headers = list(table.headers) if table.headers else list(DEFAULT_HEADERS)
    width = max([len(row) for row in rows] + [len(headers)])
    headers += [f"Kolom {index}" for index in range(len(headers) + 1, width + 1)]

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    try:
        sheet = workbook.active
        sheet.title = SHEET_NAME
        sheet.append(headers)
        for row in rows:
            padded = row + [""] * (width - len(row))
            sheet.append([_cell_value(headers[i], value) for i, value in enumerate(padded)])
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"   # nilai berawalan "=" tetap teks, bukan rumus
        sheet.freeze_panes = "A2"
        workbook.save(path)
    finally:
        workbook.close()
    return len(rows)
