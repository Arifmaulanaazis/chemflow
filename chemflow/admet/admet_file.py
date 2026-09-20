"""
Pembaca file hasil ADMETLab3 (CSV/Excel) sebagai pengganti scraping otomatis.

File diunduh pengguna dari situs ADMETLab3 dan dipetakan ke ligan secara
posisional: baris ke-N file ADMET adalah ligan ke-N pada file Excel input,
dengan urutan:

- format tidy: baris Excel dari atas ke bawah;
- format wide: kolom dari kiri ke kanan, tiap kolom dari atas ke bawah.

Jumlah baris file ADMET harus sama dengan jumlah ligan pada input. Untuk senyawa
yang muncul di beberapa grup (SMILES sama) file juga boleh memuat SMILES unik
saja: baris file dipetakan menurut urutan kemunculan pertama, lalu disalin ke
tiap ligan kembar. Jika file memuat kolom ``raw_smiles``/``smiles``, isinya
dicocokkan dengan SMILES ligan sebagai pemeriksaan urutan (ketidakcocokan hanya
menghasilkan peringatan).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from chemflow.admet.dedup import group_by_smiles

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
        Senyawa yang sama di beberapa grup (SMILES sama) mendapat salinan baris yang sama.

    Raises:
        ValueError: jumlah baris file tidak sama dengan jumlah ligan, maupun dengan
            jumlah SMILES unik.
    """
    log = logger or logging.getLogger(__name__)
    df = read_admet_table(path)
    n_ligands = len(ligand_names)

    grouping = group_by_smiles(ligand_smiles, ligand_names) if ligand_smiles is not None else None
    n_unique = len(grouping.unique_smiles) if grouping is not None else n_ligands

    if len(df) == n_ligands:
        index_of = list(range(n_ligands))
        compare_names, compare_smiles = ligand_names, ligand_smiles
    elif grouping is not None and grouping.n_duplicates > 0 and len(df) == n_unique:
        index_of = grouping.index_of
        firsts = [members[0] for members in grouping.members]
        compare_names = [ligand_names[i] for i in firsts]
        compare_smiles = grouping.unique_smiles
        log.info(
            f"File ADMET memuat {len(df)} baris = SMILES unik dari {n_ligands} ligan; hasil disalin ke "
            f"{grouping.n_duplicates} ligan kembar (senyawa yang sama di beberapa grup)."
        )
    else:
        unique_note = f" ({n_unique} SMILES unik)" if n_unique != n_ligands else ""
        raise ValueError(
            f"File ADMET '{Path(path).name}' berisi {len(df)} baris, sedangkan input memuat "
            f"{n_ligands} ligan{unique_note}. Jumlah baris harus sama dengan jumlah ligan, atau (bila ada "
            f"senyawa yang muncul di beberapa grup) dengan jumlah SMILES unik, dan berurutan: format tidy "
            f"dari atas ke bawah, format wide dari kolom kiri ke kanan (tiap kolom dari atas ke bawah)."
        )

    if compare_smiles is not None:
        _warn_on_smiles_mismatch(df, compare_names, compare_smiles, log)

    source_rows: List[Dict[str, Any]] = []
    for _, source in df.iterrows():
        source_rows.append({str(column): (None if pd.isna(value) else value)
                            for column, value in source.to_dict().items()})

    rows: List[Dict[str, Any]] = []
    for name, position in zip(ligand_names, index_of):
        record: Dict[str, Any] = {"ligand": name}
        record.update(source_rows[position])
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
