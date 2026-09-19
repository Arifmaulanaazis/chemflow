"""Header ASCII-art yang dicetak setiap kali CLI chemflow dijalankan."""

from __future__ import annotations

import sys
from typing import TextIO

# Logo chemflow (labu Erlenmeyer dengan dua simpul molekul) dirender dari chemflow.png.
# Hanya karakter ASCII agar aman dicetak di konsol Windows dengan code page apa pun.
_LOGO_LINES = (
    "               4444444444444444447",
    "               444444444444444445",
    "                 5444      4445",
    "                 5444      4445",
    "                 5444      4444",
    "                74445      54447",
    " 7544457       54444        44443",
    "2444444422225444445          54442",
    "544444444444444457            54444",
    "14444444333117                 244447",
    "  25553    71551   137          144441",
    "         344447  333333331    1  741  355555521",
    "        24445  733333333333333337   2555555555557",
    "       24445  1333333333333333331 755553     2555",
    "      14445  3333333333333333331 15555      777",
    "      24443  33333333333333333  35555     2555555",
    "      34445    777777777777   755552     155555555",
    "       2444442333333333333355555553      755555552",
    "        3444444444444445555555552         1555551",
    "           3222222222222222221",
)

_TAGLINE = "Skrining virtual senyawa obat otomatis"


def render_banner() -> str:
    """Susun teks header: logo, lalu nama, versi, dan tagline di tengah logo."""
    from chemflow import __version__

    width = max(len(line) for line in _LOGO_LINES)
    caption = (f"chemflow v{__version__}", _TAGLINE)
    return "\n".join([*_LOGO_LINES, "", *(text.center(width).rstrip() for text in caption)])


def print_banner(stream: TextIO | None = None) -> None:
    """Cetak header ke ``stream`` (default stdout), diakhiri satu baris kosong."""
    out = stream if stream is not None else sys.stdout
    print(render_banner(), file=out)
    print(file=out)
