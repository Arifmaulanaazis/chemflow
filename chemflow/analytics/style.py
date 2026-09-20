"""
Gaya visual bersama untuk seluruh grafik chemflow.

Palet kategorikal Okabe-Ito (aman untuk buta warna, Okabe & Ito 2008),
tipografi sans-serif, resolusi cetak 300 dpi, dan ekspor multi-format
(PNG untuk laporan, SVG/PDF vektor untuk naskah jurnal). Gaya diterapkan
lewat ``chart_style()`` (context manager berbasis ``rc_context``) sehingga
tidak mengubah state global matplotlib milik pemanggil.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PALETTE = [
    "#0072B2", "#D55E00", "#009E73", "#E69F00", "#56B4E9",
    "#CC79A7", "#F0E442", "#000000", "#999999", "#66C2A5",
]

COLOR_GOOD = "#009E73"
COLOR_MEDIUM = "#E69F00"
COLOR_POOR = "#D55E00"
COLOR_NEUTRAL = "#8C8C8C"
COLOR_NATIVE = "#CC79A7"   # ligan native (referensi kokristal), dibedakan dari ligan uji

MARKERS = ["o", "s", "^", "D", "v", "P", "X", "h"]

CMAP_SEQUENTIAL = "viridis"
CMAP_DIVERGING = "coolwarm"

FIG_DPI = 300
SUPPORTED_FORMATS = ("png", "svg", "pdf")

# Batas default pemotongan otomatis grafik besar (0 atau None = tidak dipotong), lihat analytics.paging.
DEFAULT_MAX_ROWS = 30       # baris/bar/ligan per gambar
DEFAULT_MAX_COLS = 20       # kolom per gambar heatmap
MAX_RADAR_SERIES = 8        # garis (ligan atau grup) per radar
MAX_RADAR_PAGES = 5         # radar per ligan dibatasi 5 bagian agar tidak jadi ratusan gambar

_RC = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlepad": 12,
    "figure.titlesize": 12,
    "figure.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.labelcolor": "#222222",
    "axes.edgecolor": "#444444",
    "axes.linewidth": 0.8,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "legend.fontsize": 9,
    "legend.frameon": False,
    "legend.title_fontsize": 9,
    "lines.linewidth": 1.6,
    "grid.color": "#DDDDDD",
    "grid.linewidth": 0.6,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "savefig.edgecolor": "none",
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
    "axes.prop_cycle": plt.cycler(color=PALETTE),
}


@contextmanager
def chart_style() -> Iterator[None]:
    """Terapkan gaya chemflow selama blok ``with`` saja."""
    with plt.rc_context(_RC):
        yield


def styled(func):
    """Dekorator: jalankan fungsi penggambar di dalam ``chart_style()``."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with chart_style():
            return func(*args, **kwargs)
    return wrapper


def clean_axes(ax, *, grid_axis: str = "") -> None:
    """Buang spine atas/kanan; grid tipis opsional pada sumbu ``"x"``, ``"y"``, atau ``"both"``."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if grid_axis:
        ax.set_axisbelow(True)
        ax.grid(True, axis=grid_axis)


_LABEL_OFFSETS = [(6, 5, "left", "bottom"), (6, -5, "left", "top"), (-6, 5, "right", "bottom"), (-6, -5, "right", "top")]


def annotate_without_overlap(ax, xs, ys, labels, *, fontsize: float = 8.0, color: str = "#333333",
                             obstacles: Sequence = ()) -> None:
    """Beri label titik dengan posisi yang dipilih agar teks tidak saling menimpa.

    Tiap label mencoba beberapa offset (kanan atas, kanan bawah, kiri atas,
    kiri bawah, lalu bertumpuk vertikal) dan memakai yang pertama tidak
    berpotongan dengan label yang sudah ditempatkan maupun dengan
    ``obstacles`` (artis teks yang sudah ada di sumbu). Batas sumbu harus
    sudah final sebelum fungsi ini dipanggil.
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    stacked = ([(6, 5 + 11 * k, "left", "bottom") for k in range(1, 7)]
               + [(6, -5 - 11 * k, "left", "top") for k in range(1, 7)])
    placed = [item.get_window_extent(renderer) for item in obstacles]
    for x, y, label in zip(xs, ys, labels):
        chosen = None
        for dx, dy, ha, va in _LABEL_OFFSETS + stacked:
            note = ax.annotate(label, (x, y), xytext=(dx, dy), textcoords="offset points",
                               ha=ha, va=va, fontsize=fontsize, color=color)
            box = note.get_window_extent(renderer)
            if not any(box.overlaps(other) for other in placed):
                chosen = box
                break
            note.remove()
        if chosen is None:
            note = ax.annotate(label, (x, y), xytext=(6, 5), textcoords="offset points",
                               ha="left", va="bottom", fontsize=fontsize, color=color)
            chosen = note.get_window_extent(renderer)
        placed.append(chosen)


def text_color_for(rgba) -> str:
    """Hitam atau putih, mana yang terbaca di atas warna sel ``rgba`` (berdasarkan luminans)."""
    red, green, blue = rgba[0], rgba[1], rgba[2]
    return "white" if 0.299 * red + 0.587 * green + 0.114 * blue < 0.5 else "black"


def color_tick_labels(labels, groups, color_map) -> None:
    """Warnai teks tick (objek ``Text``) menurut grup: ``groups[i]`` untuk ``labels[i]``."""
    for text, group in zip(labels, groups):
        color = color_map.get(group)
        if color is not None:
            text.set_color(color)


def group_colors(groups) -> dict:
    """Peta grup -> warna palet (urutan kemunculan), grup Native selalu ``COLOR_NATIVE``."""
    from chemflow.analytics.group_stats import NATIVE_GROUP

    mapping, index = {}, 0
    for group in groups:
        if group in mapping:
            continue
        if group == NATIVE_GROUP:
            mapping[group] = COLOR_NATIVE
            continue
        mapping[group] = PALETTE[index % len(PALETTE)]
        index += 1
    return mapping


def normalize_formats(formats: Sequence[str]) -> tuple:
    """Validasi daftar format; PNG selalu ikut sebagai keluaran utama."""
    cleaned = []
    for fmt in formats:
        fmt = fmt.lower().lstrip(".")
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(f"Format gambar '{fmt}' tidak didukung, pilih dari {SUPPORTED_FORMATS}.")
        if fmt not in cleaned:
            cleaned.append(fmt)
    if "png" not in cleaned:
        cleaned.insert(0, "png")
    return tuple(cleaned)


def save_figure(fig, path: "str | Path", *, dpi: int = FIG_DPI, formats: Sequence[str] = ("png",)) -> Path:
    """Simpan figure ke satu atau beberapa format, lalu tutup figure.

    Args:
        fig: objek Figure matplotlib.
        path: path keluaran utama (ekstensi ``.png``).
        dpi: resolusi raster.
        formats: format tambahan (``svg``, ``pdf``) yang ditulis berdampingan.

    Returns:
        Path file PNG utama.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stem = path.with_suffix("")
    outputs: Dict[str, Path] = {}
    for fmt in normalize_formats(formats):
        target = stem.with_suffix(f".{fmt}")
        fig.savefig(target, dpi=dpi, bbox_inches="tight", facecolor="white")
        outputs[fmt] = target
    plt.close(fig)
    return outputs["png"]
