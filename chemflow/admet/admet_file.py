"""
Pembaca file hasil ADMETLab3 (CSV/Excel) sebagai pengganti scraping otomatis.

File diunduh pengguna dari situs ADMETLab3 dan dipetakan ke ligan secara
POSISIONAL: baris ke-N file ADMET adalah ligan ke-N pada file Excel input,
dengan urutan:

- format tidy: baris Excel dari atas ke bawah;
- format wide: kolom dari kiri ke kanan, tiap kolom dari atas ke bawah.

Jumlah baris file ADMET harus sama dengan jumlah ligan pada input. Jika file
memuat kolom ``raw_smiles``/``smiles``, isinya dicocokkan dengan SMILES ligan
sebagai pemeriksaan urutan (ketidakcocokan hanya menghasilkan peringatan).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

_CSV_SUFFIXES = {".csv"}
_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


def read_admet_table(path: "str | Path") -> pd.DataFrame:
    """Baca file hasil ADMETLab3 (.csv atau .xlsx, sheet pertama).

    Raises:
        FileNotFoundError: file tidak ada.
        ValueError: ekstensi tak didukung, file kosong, atau tak terbaca.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File ADMET tidak ditemukan: {path}")

    suffix = path.suffix.lower()
    try:
        if suffix in _CSV_SUFFIXES:
            df = pd.read_csv(path)
        elif suffix in _EXCEL_SUFFIXES:
            df = pd.read_excel(path, sheet_name=0)
        else:
            raise ValueError(f"Ekstensi file ADMET '{suffix}' tidak didukung, gunakan .csv atau .xlsx.")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, OSError) as exc:
        raise ValueError(f"File ADMET '{path.name}' tidak bisa dibaca: {exc}") from exc

    if df.empty:
        raise ValueError(f"File ADMET '{path.name}' tidak berisi baris data.")
    return df


def load_admet_rows(
    path: "str | Path",
    ligand_names: Sequence[str],
    ligand_smiles: Optional[Sequence[str]] = None,
    logger: Optional[logging.Logger] = None,
) -> List[Dict[str, Any]]:
    """Petakan baris file ADMET ke ligan berdasarkan urutan input.

    Args:
        path: file hasil ADMETLab3.
        ligand_names: nama ligan (sudah disanitasi) sesuai urutan input Excel.
        ligand_smiles: SMILES tiap ligan (opsional, untuk pemeriksaan urutan);
            entri kosong dilewati.
        logger: logger opsional.

    Returns:
        Satu dict per ligan, berisi ``"ligand"`` dan seluruh kolom file ADMET.

    Raises:
        ValueError: jumlah baris file tidak sama dengan jumlah ligan.
    """
    log = logger or logging.getLogger(__name__)
    df = read_admet_table(path)

    if len(df) != len(ligand_names):
        raise ValueError(
            f"File ADMET '{Path(path).name}' berisi {len(df)} baris, sedangkan input memuat "
            f"{len(ligand_names)} ligan. Jumlah harus sama dan berurutan: format tidy dari atas ke "
            f"bawah, format wide dari kolom kiri ke kanan (tiap kolom dari atas ke bawah)."
        )

    if ligand_smiles is not None:
        _warn_on_smiles_mismatch(df, ligand_names, ligand_smiles, log)

    rows: List[Dict[str, Any]] = []
    for name, (_, source) in zip(ligand_names, df.iterrows()):
        record: Dict[str, Any] = {"ligand": name}
        for column, value in source.to_dict().items():
            record[str(column)] = None if pd.isna(value) else value
        rows.append(record)

    log.info(f"ADMET dimuat dari file '{Path(path).name}': {len(rows)} ligan.")
    return rows


def _canonical(smiles: Any) -> Optional[str]:
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(str(smiles))
        return Chem.MolToSmiles(mol) if mol is not None else None
    except Exception:
        return None


def _warn_on_smiles_mismatch(df: pd.DataFrame, names: Sequence[str], smiles: Sequence[str],
                              log: logging.Logger) -> None:
    column = next((c for c in ("raw_smiles", "smiles") if c in df.columns), None)
    if column is None:
        return

    mismatched = []
    for name, expected, found in zip(names, smiles, df[column]):
        if not expected:
            continue
        canonical_expected, canonical_found = _canonical(expected), _canonical(found)
        if canonical_expected and canonical_found and canonical_expected != canonical_found:
            mismatched.append(name)

    if mismatched:
        preview = ", ".join(mismatched[:5]) + (" ..." if len(mismatched) > 5 else "")
        log.warning(
            f"SMILES pada file ADMET tidak cocok dengan SMILES input untuk {len(mismatched)} ligan "
            f"({preview}). Periksa apakah urutan baris file ADMET sama dengan urutan ligan input."
        )
