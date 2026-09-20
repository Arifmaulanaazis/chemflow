"""
Pemotongan otomatis (auto-split) grafik besar menjadi beberapa bagian.

Grafik dengan puluhan ligan atau reseptor menjadi kecil dan sulit dibaca bila
dipaksa dalam satu gambar. Modul ini membagi ``n`` item menjadi halaman yang
seimbang (25 item dengan batas 20 menjadi 13 + 12, bukan 20 + 5) dan
menyediakan akhiran nama file ``_part02of03``. Tanpa pemotongan, nama file
tidak berubah.

Pemanggil wajib menghitung skala warna, normalisasi, dan batas sumbu secara
global sebelum memotong, supaya antar-bagian tetap sebanding.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Page:
    """Satu bagian dari daftar item: indeks 1-based, rentang ``[start, stop)`` 0-based."""
    index: int
    total: int
    start: int
    stop: int

    @property
    def count(self) -> int:
        return self.stop - self.start

    @property
    def is_single(self) -> bool:
        return self.total == 1

    @property
    def suffix(self) -> str:
        return "" if self.total == 1 else f"_part{self.index:02d}of{self.total:02d}"

    @property
    def title_suffix(self) -> str:
        return "" if self.total == 1 else f" (bagian {self.index}/{self.total})"

    def slice(self, items):
        return items[self.start:self.stop]


@dataclass(frozen=True)
class Tile:
    """Satu ubin pada kisi baris x kolom: dipakai heatmap yang terlalu besar di kedua sumbu."""
    index: int
    total: int
    rows: Page
    cols: Page

    @property
    def is_single(self) -> bool:
        return self.total == 1

    @property
    def suffix(self) -> str:
        return "" if self.total == 1 else f"_part{self.index:02d}of{self.total:02d}"

    @property
    def title_suffix(self) -> str:
        if self.total == 1:
            return ""
        parts = []
        if self.rows.total > 1:
            parts.append(f"baris {self.rows.start + 1}-{self.rows.stop}")
        if self.cols.total > 1:
            parts.append(f"kolom {self.cols.start + 1}-{self.cols.stop}")
        return f" (bagian {self.index}/{self.total}: {', '.join(parts)})"


def paginate(n_items: int, max_items: Optional[int]) -> List[Page]:
    """Bagi ``n_items`` menjadi halaman seimbang berisi paling banyak ``max_items``.

    Args:
        n_items: jumlah item.
        max_items: batas per halaman; ``None`` atau ``<= 0`` berarti tidak dipotong.

    Returns:
        Daftar ``Page`` (kosong bila ``n_items <= 0``).
    """
    if n_items <= 0:
        return []
    if not max_items or max_items <= 0 or n_items <= max_items:
        return [Page(1, 1, 0, n_items)]

    total = ceil(n_items / max_items)
    base, extra = divmod(n_items, total)
    pages: List[Page] = []
    start = 0
    for i in range(total):
        size = base + (1 if i < extra else 0)
        pages.append(Page(i + 1, total, start, start + size))
        start += size
    return pages


def paginate_grid(n_rows: int, n_cols: int, max_rows: Optional[int], max_cols: Optional[int]) -> List[Tile]:
    """Bagi kisi ``n_rows x n_cols`` menjadi ubin, berurutan baris demi baris."""
    row_pages = paginate(n_rows, max_rows)
    col_pages = paginate(n_cols, max_cols)
    total = len(row_pages) * len(col_pages)
    tiles: List[Tile] = []
    for row_page in row_pages:
        for col_page in col_pages:
            tiles.append(Tile(len(tiles) + 1, total, row_page, col_page))
    return tiles


def paged_name(filename: str, page: "Page | Tile") -> str:
    """Sisipkan akhiran bagian sebelum ekstensi; nama tak berubah bila hanya satu bagian."""
    if page.suffix == "":
        return filename
    path = Path(filename)
    return f"{path.stem}{page.suffix}{path.suffix}"
