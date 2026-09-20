"""
Pustaka senyawa untuk memberi nama pada puncak: pustaka pengguna (nama, RT atau RI,
CAS, SMILES), indeks retensi Kovats dari deret alkana, dan daftar alergen wewangian
Uni Eropa.

Data GC-MS berupa TIC saja tidak membawa nama senyawa. Nama datang dari tiga sumber:
kolom Name pada laporan puncak instrumen, pustaka pengguna yang dicocokkan lewat RT
(hasil injeksi standar) atau RI, dan nomor CAS. Pencocokan nama bersifat persis
setelah normalisasi (bukan mengandung), supaya "linalool oxide" tidak dianggap
"linalool".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Compound:
    """Satu senyawa pustaka. ``rt`` dalam menit; ``ri`` indeks retensi Kovats."""
    name: str
    cas: str = ""
    smiles: str = ""
    rt: Optional[float] = None
    ri: Optional[float] = None
    aliases: Tuple[str, ...] = ()
    note: str = ""


def name_key(name: str) -> str:
    """Kunci pencocokan nama: huruf kecil tanpa penanda stereo dan tanpa tanda baca."""
    text = name.lower().strip()
    text = re.sub(r"\((?:e|z|r|s|\+|-|±|rs)\)-?", "", text)
    text = re.sub(r"^(?:d|l|dl|cis|trans|e|z)-", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def _allergen(name: str, cas: str, smiles: str, *aliases: str) -> Compound:
    return Compound(name=name, cas=cas, smiles=smiles, aliases=tuple(aliases), note="Alergen wewangian UE (26 senyawa)")


# 24 senyawa tunggal dari daftar 26 alergen wewangian Uni Eropa (Regulasi Kosmetik 1223/2009, Lampiran III,
# berasal dari SCCNFP/0017/98). Dua sisanya, ekstrak lumut pohon ek (Evernia prunastri, CAS 90028-68-5) dan
# lumut pohon (Evernia furfuracea, CAS 90028-67-4), adalah campuran alami tanpa satu struktur.
EU_ALLERGENS: Tuple[Compound, ...] = (
    _allergen("Amyl cinnamal", "122-40-7", "CCCCCC(=Cc1ccccc1)C=O", "alpha-amylcinnamaldehyde", "Heptanal, 2-(phenylmethylene)-"),
    _allergen("Amylcinnamyl alcohol", "101-85-9", "CCCCCC(=Cc1ccccc1)CO", "alpha-amylcinnamyl alcohol"),
    _allergen("Anisyl alcohol", "105-13-5", "COc1ccc(CO)cc1", "4-methoxybenzyl alcohol", "Benzenemethanol, 4-methoxy-"),
    _allergen("Benzyl alcohol", "100-51-6", "OCc1ccccc1", "Benzenemethanol"),
    _allergen("Benzyl benzoate", "120-51-4", "O=C(OCc1ccccc1)c1ccccc1", "Benzoic acid, phenylmethyl ester"),
    _allergen("Benzyl cinnamate", "103-41-3", "O=C(/C=C/c1ccccc1)OCc1ccccc1", "2-Propenoic acid, 3-phenyl-, phenylmethyl ester"),
    _allergen("Benzyl salicylate", "118-58-1", "O=C(OCc1ccccc1)c1ccccc1O", "Benzoic acid, 2-hydroxy-, phenylmethyl ester"),
    _allergen("Cinnamal", "104-55-2", "O=C/C=C/c1ccccc1", "cinnamaldehyde", "2-Propenal, 3-phenyl-"),
    _allergen("Cinnamyl alcohol", "104-54-1", "OC/C=C/c1ccccc1", "2-Propen-1-ol, 3-phenyl-"),
    _allergen("Citral", "5392-40-5", "CC(C)=CCC/C(C)=C/C=O", "geranial", "neral", "2,6-Octadienal, 3,7-dimethyl-"),
    _allergen("Citronellol", "106-22-9", "CC(C)=CCCC(C)CCO", "6-Octen-1-ol, 3,7-dimethyl-"),
    _allergen("Coumarin", "91-64-5", "O=c1ccc2ccccc2o1", "2H-1-Benzopyran-2-one"),
    _allergen("Eugenol", "97-53-0", "C=CCc1ccc(O)c(OC)c1", "Phenol, 2-methoxy-4-(2-propenyl)-"),
    _allergen("Farnesol", "4602-84-0", "CC(C)=CCC/C(C)=C/CC/C(C)=C/CO", "2,6,10-Dodecatrien-1-ol, 3,7,11-trimethyl-"),
    _allergen("Geraniol", "106-24-1", "CC(C)=CCC/C(C)=C/CO", "2,6-Octadien-1-ol, 3,7-dimethyl-"),
    _allergen("Hexyl cinnamal", "101-86-0", "CCCCCCC(=Cc1ccccc1)C=O", "alpha-hexylcinnamaldehyde", "Octanal, 2-(phenylmethylene)-"),
    _allergen("Hydroxycitronellal", "107-75-5", "O=CCC(C)CCCC(C)(C)O", "Octanal, 7-hydroxy-3,7-dimethyl-"),
    _allergen("Hydroxyisohexyl 3-cyclohexene carboxaldehyde", "31906-04-4", "CC(C)(O)CCCC1=CCC(C=O)CC1", "HICC", "Lyral",
              "3-Cyclohexene-1-carboxaldehyde, 4-(4-hydroxy-4-methylpentyl)-"),
    _allergen("Isoeugenol", "97-54-1", "C/C=C/c1ccc(O)c(OC)c1", "Phenol, 2-methoxy-4-(1-propenyl)-"),
    _allergen("Limonene", "5989-27-5", "CC1=CCC(CC1)C(C)=C", "d-limonene", "dl-limonene", "dipentene", "138-86-3",
              "Cyclohexene, 1-methyl-4-(1-methylethenyl)-"),
    _allergen("Linalool", "78-70-6", "CC(C)=CCCC(C)(O)C=C", "1,6-Octadien-3-ol, 3,7-dimethyl-"),
    _allergen("Methyl 2-octynoate", "111-12-6", "CCCCCC#CC(=O)OC", "methyl heptine carbonate", "2-Octynoic acid, methyl ester"),
    _allergen("alpha-Isomethyl ionone", "127-51-5", "CC(=O)C(C)=CC1C(C)=CCCC1(C)C", "isomethyl-alpha-ionone",
              "3-Buten-2-one, 3-methyl-4-(2,6,6-trimethyl-2-cyclohexen-1-yl)-"),
    _allergen("Butylphenyl methylpropional", "80-54-6", "CC(C)(C)c1ccc(CC(C)C=O)cc1", "lilial", "BMHCA",
              "Benzenepropanal, 4-(1,1-dimethylethyl)-.alpha.-methyl-"),
)


def _index(compounds: Sequence[Compound]) -> Tuple[Dict[str, Compound], Dict[str, Compound]]:
    by_name: Dict[str, Compound] = {}
    by_cas: Dict[str, Compound] = {}
    for compound in compounds:
        for label in (compound.name, *compound.aliases):
            if re.fullmatch(r"\d{2,7}-\d{2}-\d", label):
                by_cas.setdefault(label, compound)
            else:
                by_name.setdefault(name_key(label), compound)
        if compound.cas:
            by_cas.setdefault(compound.cas, compound)
    return by_name, by_cas


def match_by_name(names: Sequence[str], cas_numbers: Sequence[str],
                  compounds: Sequence[Compound] = EU_ALLERGENS) -> Dict[int, Compound]:
    """Indeks fitur (posisi pada ``names``) ke senyawa pustaka, dicocokkan lewat CAS atau nama persis."""
    by_name, by_cas = _index(compounds)
    found: Dict[int, Compound] = {}
    for i, name in enumerate(names):
        cas = cas_numbers[i].strip() if i < len(cas_numbers) else ""
        hit = by_cas.get(cas) if cas else None
        if hit is None and name:
            hit = by_name.get(name_key(name))
        if hit is not None:
            found[i] = hit
    return found


def load_library(path: "str | Path") -> List[Compound]:
    """Pustaka pengguna dari CSV/TSV/Excel.

    Kolom dikenali dari judulnya (huruf besar kecil bebas): ``name``/``nama``/``compound``,
    ``rt`` (menit), ``ri``, ``cas``, ``smiles``. Minimal satu dari ``rt`` dan ``ri`` dibutuhkan
    agar senyawa bisa dicocokkan ke puncak; tanpa keduanya senyawa hanya dipakai lewat nama.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Pustaka senyawa tidak ditemukan: {path}")
    frame = pd.read_excel(path) if path.suffix.lower() in (".xls", ".xlsx", ".xlsm") else pd.read_csv(path, sep=None, engine="python")
    lookup = {str(c).strip().lower(): c for c in frame.columns}

    def column(*names: str) -> Optional[str]:
        return next((lookup[n] for n in names if n in lookup), None)

    name_col = column("name", "nama", "compound", "senyawa", "component")
    if name_col is None:
        raise ValueError(f"Pustaka {path.name} butuh kolom nama (name/nama/compound). Kolom ada: {list(frame.columns)}")
    rt_col = column("rt", "ret.time", "retention time", "rt (min)", "waktu retensi")
    ri_col, cas_col, smiles_col = column("ri", "kovats", "kovats ri", "lri"), column("cas", "cas#", "cas no"), column("smiles")

    def number(row, col) -> Optional[float]:
        if col is None or pd.isna(row[col]):
            return None
        try:
            return float(row[col])
        except (TypeError, ValueError):
            return None

    def label(row, col) -> str:
        return "" if col is None or pd.isna(row[col]) else str(row[col]).strip()

    compounds = [Compound(name=label(row, name_col), cas=label(row, cas_col), smiles=label(row, smiles_col),
                          rt=number(row, rt_col), ri=number(row, ri_col))
                 for _, row in frame.iterrows() if label(row, name_col)]
    if not compounds:
        raise ValueError(f"Pustaka {path.name} tidak berisi baris senyawa.")
    return compounds


def load_alkanes(path: "str | Path") -> Tuple[np.ndarray, np.ndarray]:
    """Deret alkana untuk indeks Kovats dari CSV/TSV/Excel dengan kolom ``carbon`` (jumlah C) dan ``rt`` (menit)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Berkas deret alkana tidak ditemukan: {path}")
    frame = pd.read_excel(path) if path.suffix.lower() in (".xls", ".xlsx", ".xlsm") else pd.read_csv(path, sep=None, engine="python")
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    carbon = next((lookup[n] for n in ("carbon", "c", "n", "karbon", "carbon number") if n in lookup), None)
    rt = next((lookup[n] for n in ("rt", "ret.time", "retention time", "rt (min)") if n in lookup), None)
    if carbon is None or rt is None:
        raise ValueError(f"Deret alkana butuh kolom 'carbon' dan 'rt'. Kolom ada: {list(frame.columns)}")
    data = frame[[carbon, rt]].dropna().astype(float).sort_values(rt)
    if len(data) < 3:
        raise ValueError("Deret alkana butuh minimal 3 titik.")
    return data[carbon].to_numpy(), data[rt].to_numpy()


def kovats_index(rt: Sequence[float], carbons: np.ndarray, alkane_rt: np.ndarray) -> np.ndarray:
    """Indeks retensi Kovats terprogram suhu (van den Dool dan Kratz): interpolasi linear antar alkana. NaN di luar deret."""
    rt = np.asarray(rt, dtype=float)
    index = 100.0 * np.interp(rt, alkane_rt, carbons)
    return np.where((rt < alkane_rt[0]) | (rt > alkane_rt[-1]), np.nan, index)


def match_by_retention(rts: Sequence[float], ris: Optional[Sequence[float]], compounds: Sequence[Compound],
                       rt_tolerance: float = 0.05, ri_tolerance: float = 10.0) -> Dict[int, Tuple[Compound, float]]:
    """Cocokkan fitur ke pustaka lewat RT (menit) atau RI: indeks fitur ke (senyawa, selisih).

    Tiap senyawa hanya dipakai satu kali, oleh fitur terdekat. Bila ``ri`` tersedia di kedua sisi,
    RI didahulukan; kalau tidak, RT.
    """
    candidates: List[Tuple[float, int, int]] = []
    for c_index, compound in enumerate(compounds):
        for f_index, rt in enumerate(rts):
            ri = ris[f_index] if ris is not None else float("nan")
            if compound.ri is not None and np.isfinite(ri):
                delta, limit = abs(ri - compound.ri), ri_tolerance
            elif compound.rt is not None:
                delta, limit = abs(rt - compound.rt), rt_tolerance
            else:
                continue
            if delta <= limit:
                candidates.append((delta / limit, f_index, c_index))
    matched: Dict[int, Tuple[Compound, float]] = {}
    used = set()
    for score, f_index, c_index in sorted(candidates):
        if f_index in matched or c_index in used:
            continue
        matched[f_index] = (compounds[c_index], score)
        used.add(c_index)
    return matched
