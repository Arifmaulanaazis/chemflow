"""
Pembaca Excel untuk data reseptor. Kode PDB wajib, kolom gridbox opsional
(pusat x/y/z, ukuran x/y/z, atau ukuran seragam satu kolom).

Baris dengan kode PDB duplikat didukung dan bukan dianggap error. Ini
memungkinkan multi-situs docking (reseptor sama, gridbox/binding-site
berbeda per baris).
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import List, NamedTuple, Optional

import pandas as pd

from chemflow.utils.name_sanitizer import sanitize_filename


class ReceptorEntry(NamedTuple):
    """Satu baris data reseptor dari Excel.

    ``center_x/y/z`` bernilai ``None`` jika kolom gridbox tak ditemukan;
    pipeline akan jatuh ke deteksi ligan native / input manual.
    ``row_index`` (1-based) dipakai untuk membuat kunci unik reseptor saat
    kode PDB duplikat (multi-situs).
    """
    pdb_code: str
    row_index: int
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    center_z: Optional[float] = None
    size_x: Optional[float] = None
    size_y: Optional[float] = None
    size_z: Optional[float] = None
    uniform_size: Optional[float] = None
    label: Optional[str] = None

    @property
    def has_gridbox_center(self) -> bool:
        return self.center_x is not None and self.center_y is not None and self.center_z is not None

    @property
    def unique_key(self) -> str:
        """Kunci unik reseptor: kode PDB + nomor baris jika ada duplikat."""
        suffix = f"_R{self.row_index:03d}"
        return f"{sanitize_filename(self.pdb_code)}{suffix}"


def read_receptors(
    excel_path: str | Path,
    *,
    pdb_col: Optional[str] = None,
    cx_col: Optional[str] = None,
    cy_col: Optional[str] = None,
    cz_col: Optional[str] = None,
    sx_col: Optional[str] = None,
    sy_col: Optional[str] = None,
    sz_col: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> List[ReceptorEntry]:
    """Baca kode PDB (dan gridbox opsional per baris) dari Excel.

    Args:
        excel_path: path file .xlsx/.xls.
        pdb_col..sz_col: override kolom manual; ``None`` = auto-detect
            berdasar keyword pada nama kolom.
        logger: logger opsional.

    Returns:
        Daftar ``ReceptorEntry``, duplikat kode PDB dipertahankan (bukan
        dedup) untuk mendukung multi-situs docking.

    Raises:
        FileNotFoundError: file tak ditemukan.
        ValueError: kolom kode PDB tak bisa di-resolve, atau tak ada baris valid.
    """
    log = logger or logging.getLogger(__name__)
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"File Excel reseptor tidak ditemukan: {path}")

    df = pd.read_excel(str(path), dtype=str)
    df.columns = df.columns.str.strip()
    cols = list(df.columns)
    log.info(f"[Reseptor] Membaca: {path.name}, kolom: {cols}")

    resolved_pdb = pdb_col or _auto_detect(cols, "pdb code") or _auto_detect(cols, "pdb")
    if resolved_pdb is None:
        raise ValueError(
            f"Kolom kode PDB tidak ditemukan/tidak bisa di-auto-detect. "
            f"Kolom tersedia: {cols}. Tentukan secara eksplisit lewat --receptor-pdb-col."
        )

    resolved_cx = cx_col or _auto_detect(cols, "center_x") or _auto_detect(cols, "cx")
    resolved_cy = cy_col or _auto_detect(cols, "center_y") or _auto_detect(cols, "cy")
    resolved_cz = cz_col or _auto_detect(cols, "center_z") or _auto_detect(cols, "cz")
    resolved_sx = sx_col or _auto_detect(cols, "size_x") or _auto_detect(cols, "sx")
    resolved_sy = sy_col or _auto_detect(cols, "size_y") or _auto_detect(cols, "sy")
    resolved_sz = sz_col or _auto_detect(cols, "size_z") or _auto_detect(cols, "sz")
    resolved_uniform = _auto_detect(cols, "gridbox") or _auto_detect(cols, "box_size")
    resolved_label = _auto_detect(cols, "label") or _auto_detect(cols, "site")

    gb_found = [c for c in (resolved_cx, resolved_cy, resolved_cz) if c]
    if len(gb_found) == 3:
        log.info(f"[Reseptor] Kolom gridbox ditemukan: {resolved_cx}, {resolved_cy}, {resolved_cz}")
    elif gb_found:
        log.warning(
            f"[Reseptor] Kolom gridbox tidak lengkap ({gb_found}), butuh ketiganya "
            f"(x,y,z). Baris tanpa gridbox lengkap akan pakai deteksi ligan native/manual."
        )

    entries: List[ReceptorEntry] = []
    skipped = 0
    for row_idx, (_, row) in enumerate(df.iterrows(), start=1):
        code = _safe_str(row.get(resolved_pdb))
        if not code:
            skipped += 1
            continue
        code = code.strip().upper()

        entries.append(ReceptorEntry(
            pdb_code=code,
            row_index=row_idx,
            center_x=_safe_float(row.get(resolved_cx) if resolved_cx else None),
            center_y=_safe_float(row.get(resolved_cy) if resolved_cy else None),
            center_z=_safe_float(row.get(resolved_cz) if resolved_cz else None),
            size_x=_safe_float(row.get(resolved_sx) if resolved_sx else None),
            size_y=_safe_float(row.get(resolved_sy) if resolved_sy else None),
            size_z=_safe_float(row.get(resolved_sz) if resolved_sz else None),
            uniform_size=_safe_float(row.get(resolved_uniform) if resolved_uniform else None),
            label=_safe_str(row.get(resolved_label) if resolved_label else None) or None,
        ))

    if skipped:
        log.warning(f"[Reseptor] {skipped} baris dilewati (kode PDB kosong).")
    if not entries:
        raise ValueError(f"Tidak ada baris reseptor valid ditemukan di {path}")

    dup_counts = Counter(e.pdb_code for e in entries)
    dups = {c: n for c, n in dup_counts.items() if n > 1}
    for code, n in dups.items():
        log.info(f"[Reseptor] Kode PDB '{code}' muncul {n}x (multi-situs docking).")

    log.info(f"[Reseptor] {len(entries)} baris reseptor dimuat ({len(dup_counts)} kode PDB unik).")
    return entries


def _auto_detect(cols: List[str], keyword: str) -> Optional[str]:
    kw = keyword.lower()
    for col in cols:
        if kw in col.lower():
            return col
    return None


def _safe_str(val: object) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "") else s


def _safe_float(val: object) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ("nan", "none", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None
