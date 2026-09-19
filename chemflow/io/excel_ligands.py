"""
Pembaca Excel untuk data ligan. Mendukung dua format sekaligus, dideteksi
otomatis:

  1. **Tidy** (panjang): satu baris = satu senyawa, ada kolom nama & SMILES
     (SMILES boleh kosong -> akan di-resolve lewat PubChem), kolom
     ``group``/``sumber`` opsional untuk pengelompokan PCA.

  2. **Wide** (lebar, multi-kolom): tidak ada kolom SMILES sama sekali;
     tiap kolom berisi daftar nama senyawa dan HEADER kolom itu sendiri
     menjadi label kelompok (mis. kolom "Tanaman_X" berisi daftar nama
     senyawa dari tanaman X). Panjang tiap kolom boleh berbeda, sel
     kosong/NaN diabaikan.

Strategi deteksi: kalau ditemukan kolom yang cocok keyword "smiles" ->
mode tidy. Kalau tidak, dan ada >=1 kolom yang isinya teks (bukan angka)
-> mode wide (setiap kolom jadi satu grup).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, NamedTuple, Optional

import pandas as pd

from chemflow.utils.name_sanitizer import sanitize_filename, unique_safe_names


class LigandRecord(NamedTuple):
    """Satu senyawa yang akan diproses pipeline.

    Attributes:
        name: nama senyawa (dari Excel).
        smiles: SMILES, kosong string jika belum ada (perlu resolusi PubChem).
        group: label kelompok sumber (nama kolom pada mode wide, atau isi
            kolom "group" pada mode tidy). ``None`` jika tak ada informasi
            kelompok sama sekali (mis. hanya 1 kolom tidy tanpa kolom group).
        safe_name: nama aman untuk file dan folder, unik di antara seluruh
            senyawa. Diisi oleh ``read_ligands``.
    """
    name: str
    smiles: str
    group: Optional[str] = None
    safe_name: str = ""

    @property
    def needs_pubchem_lookup(self) -> bool:
        return not bool(self.smiles and self.smiles.strip())


def read_ligands(
    excel_path: str | Path,
    *,
    name_col: Optional[str] = None,
    smiles_col: Optional[str] = None,
    group_col: Optional[str] = None,
    max_name_length: int = 60,
    logger: Optional[logging.Logger] = None,
) -> List[LigandRecord]:
    """Baca file Excel ligan, auto-deteksi format tidy vs wide-multigroup.

    Args:
        excel_path: path file .xlsx/.xls.
        name_col: override kolom nama (mode tidy).
        smiles_col: override kolom SMILES (mode tidy), memaksa mode tidy.
        group_col: override kolom kelompok (mode tidy).
        max_name_length: panjang maksimum ``safe_name`` (nama file/folder ligan).
        logger: logger opsional.

    Returns:
        Daftar ``LigandRecord``, urutan sesuai baris/kolom asli.

    Raises:
        FileNotFoundError: file tak ditemukan.
        ValueError: file terbaca tapi tak ada senyawa valid sama sekali,
            atau strukturnya tak bisa diklasifikasikan (tidy/wide).
    """
    log = logger or logging.getLogger(__name__)
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"File Excel ligan tidak ditemukan: {path}")

    df = pd.read_excel(str(path), dtype=str)
    df.columns = df.columns.str.strip()
    log.info(f"[Ligan] Membaca: {path.name}, kolom: {list(df.columns)}")

    resolved_smiles = smiles_col or _auto_detect(list(df.columns), "smiles")

    if resolved_smiles is not None or smiles_col is not None:
        records = _read_tidy(df, name_col=name_col, smiles_col=resolved_smiles,
                              group_col=group_col, logger=log)
    else:
        records = _read_wide(df, logger=log)

    if not records:
        raise ValueError(f"Tidak ada data senyawa valid ditemukan di {path}")

    safe_names = unique_safe_names([r.name for r in records], max_length=max_name_length)
    records = [r._replace(safe_name=safe) for r, safe in zip(records, safe_names)]
    for record in records:
        if record.safe_name != sanitize_filename(record.name, max_length=max_name_length):
            log.warning(
                f"[Ligan] Nama '{record.name}' bentrok dengan senyawa lain setelah sanitasi nama file, "
                f"dipakai '{record.safe_name}'."
            )

    n_missing_smiles = sum(1 for r in records if r.needs_pubchem_lookup)
    n_groups = len({r.group for r in records if r.group})
    log.info(
        f"[Ligan] {len(records)} senyawa dimuat "
        f"({n_missing_smiles} perlu resolusi PubChem, {n_groups} kelompok terdeteksi)."
    )
    return records


def _read_tidy(
    df: pd.DataFrame,
    *,
    name_col: Optional[str],
    smiles_col: Optional[str],
    group_col: Optional[str],
    logger: logging.Logger,
) -> List[LigandRecord]:
    """Mode tidy: satu baris = satu senyawa."""
    cols = list(df.columns)
    resolved_name = name_col or _auto_detect(cols, "compound name") or _auto_detect(cols, "name")
    if resolved_name is None:
        raise ValueError(
            f"Mode tidy terdeteksi (ada kolom SMILES) tapi kolom nama senyawa "
            f"tidak ditemukan. Kolom tersedia: {cols}"
        )
    resolved_smiles = smiles_col or _auto_detect(cols, "smiles")
    resolved_group = group_col or _auto_detect(cols, "group") or _auto_detect(cols, "sumber") \
        or _auto_detect(cols, "source")

    logger.info(
        f"[Ligan] Mode TIDY: nama='{resolved_name}', smiles='{resolved_smiles}', "
        f"group='{resolved_group}'"
    )

    records: List[LigandRecord] = []
    skipped = 0
    for _, row in df.iterrows():
        name = _safe_str(row.get(resolved_name))
        if not name:
            skipped += 1
            continue
        smiles = _safe_str(row.get(resolved_smiles)) if resolved_smiles else ""
        group = _safe_str(row.get(resolved_group)) or None if resolved_group else None
        records.append(LigandRecord(name=name, smiles=smiles, group=group))

    if skipped:
        logger.warning(f"[Ligan] {skipped} baris dilewati (nama kosong).")
    return records


def _read_wide(df: pd.DataFrame, *, logger: logging.Logger) -> List[LigandRecord]:
    """Mode wide: tiap kolom = satu kelompok, isi sel = nama senyawa."""
    cols = list(df.columns)
    logger.info(f"[Ligan] Mode WIDE (multi-kolom kelompok), kolom: {cols}")

    records: List[LigandRecord] = []
    for col in cols:
        group_label = str(col).strip()
        if not group_label:
            continue
        for raw_val in df[col]:
            name = _safe_str(raw_val)
            if not name:
                continue
            records.append(LigandRecord(name=name, smiles="", group=group_label))

    return records


def _auto_detect(cols: List[str], keyword: str) -> Optional[str]:
    """Kolom pertama yang namanya mengandung *keyword* (case-insensitive)."""
    kw = keyword.lower()
    for col in cols:
        if kw in col.lower():
            return col
    return None


def _safe_str(val: object) -> str:
    """Konversi sel Excel ke string bersih; NaN/None -> string kosong."""
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "") else s
