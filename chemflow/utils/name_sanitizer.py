"""Sanitasi nama senyawa/reseptor menjadi nama file & kode singkat yang aman."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import List, Sequence

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_EDGE_CHARS = "._-"

_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
)

_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta",
    "θ": "theta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi",
    "π": "pi", "ρ": "rho", "σ": "sigma", "ς": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi",
    "χ": "chi", "ψ": "psi", "ω": "omega",
    "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Π": "Pi", "Σ": "Sigma",
    "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
}
_LATIN = {
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D", "ð": "d", "þ": "th", "ł": "l", "Ł": "L",
}
_TRANSLITERATION = str.maketrans({**_GREEK, **_LATIN})


def _to_ascii(text: str) -> str:
    """Ubah huruf beraksen dan huruf Yunani ke padanan ASCII, buang karakter lain di luar ASCII."""
    decomposed = unicodedata.normalize("NFKD", text or "").translate(_TRANSLITERATION)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def sanitize_filename(name: str, max_length: int = 60, fallback: str = "unnamed") -> str:
    """Ubah string bebas menjadi nama file yang aman di Windows, macOS, dan Linux.

    Karakter terlarang (``< > : " / \\ | ? *`` dan karakter kontrol), spasi,
    serta titik/spasi di ujung nama dibuang. Huruf beraksen diubah ke huruf
    dasarnya, huruf Yunani ditulis namanya (alpha, beta, ...), nama perangkat
    Windows (CON, NUL, COM1, dst.) diberi garis bawah, dan nama yang tidak
    menyisakan huruf atau angka sama sekali (mis. aksara non-Latin) diberi
    akhiran hash agar tetap unik.

    Args:
        name: nama asli (mis. nama senyawa dari Excel).
        max_length: panjang maksimum hasil (menjaga path di bawah batas 260
            karakter Windows).
        fallback: dasar nama jika tidak ada karakter yang bisa dipertahankan.

    Returns:
        String yang aman dipakai sebagai nama file/direktori.
    """
    cleaned = re.sub(r"_+", "_", _UNSAFE_CHARS.sub("_", _to_ascii(name))).strip(_EDGE_CHARS)

    if not any(ch.isalnum() for ch in cleaned):
        if not (name or "").strip():
            return fallback
        return f"{fallback}_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"

    cleaned = cleaned[:max_length].strip(_EDGE_CHARS)
    base, dot, rest = cleaned.partition(".")
    if base.upper() in _WINDOWS_RESERVED:
        cleaned = f"{base}_{dot}{rest}"
    return cleaned


def unique_safe_names(names: Sequence[str], max_length: int = 60) -> List[str]:
    """Sanitasi tiap nama dan pastikan hasilnya unik tanpa membedakan huruf besar/kecil.

    Windows dan macOS memperlakukan ``Aspirin`` dan ``aspirin`` sebagai satu
    file, jadi nama yang bentrok diberi akhiran ``_2``, ``_3``, dan seterusnya
    menurut urutan kemunculan.
    """
    used = set()
    result: List[str] = []
    for name in names:
        base = sanitize_filename(name, max_length=max_length)
        candidate, counter = base, 1
        while candidate.lower() in used:
            counter += 1
            suffix = f"_{counter}"
            candidate = f"{base[:max_length - len(suffix)]}{suffix}"
        used.add(candidate.lower())
        result.append(candidate)
    return result


def derive_pdb_resname(name: str, code: str = "") -> str:
    """Turunkan nama residu PDB (tepat 3 karakter, alfanumerik) dari nama senyawa/kode.

    Format PDB mewajibkan kolom resName tepat 3 karakter. Fungsi ini
    mengambil karakter alfanumerik dari nama (diutamakan) atau kode,
    membuang digit di awal (residu PDB konvensinya diawali huruf), lalu
    memotong/mengisi ke 3 karakter.

    Args:
        name: nama senyawa (diutamakan sebagai sumber).
        code: kode fallback jika nama kosong/tidak menghasilkan karakter valid.

    Returns:
        String 3 karakter uppercase, atau ``"LIG"`` jika keduanya gagal.
    """
    for src in (name, code):
        if not src:
            continue
        alnum = "".join(ch for ch in _to_ascii(src).upper() if ch.isalnum()).lstrip("0123456789")
        if alnum:
            return (alnum + "XXX")[:3]
    return "LIG"
