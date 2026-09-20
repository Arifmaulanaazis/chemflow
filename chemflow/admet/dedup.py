"""
Penyalinan hasil ADMET untuk senyawa yang muncul lebih dari sekali.

Senyawa A yang ada di grup 1 dan grup 2 menjadi dua ligan (dua ``LigandRecord``)
dengan SMILES sama. Prediksi ADMET hanya perlu dilakukan sekali per SMILES
unik; hasilnya disalin ke tiap ligan menurut urutan (indeks) saat dikirim.
Dengan begitu nilai ADMET senyawa yang sama identik di semua grup, dan file
ADMET hasil unduhan manual boleh memuat baris unik saja.

Kunci kesamaan: SMILES kanonik RDKit; SMILES yang tak terbaca memakai teks
aslinya; SMILES kosong memakai nama senyawa (huruf kecil).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


def canonical_key(smiles: Optional[str], name: str = "") -> str:
    """Kunci kesamaan satu ligan (lihat docstring modul)."""
    text = (smiles or "").strip()
    if not text:
        return f"name:{(name or '').strip().casefold()}"
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(text)
        if mol is not None:
            return f"smi:{Chem.MolToSmiles(mol)}"
    except Exception:
        pass
    return f"raw:{text}"


@dataclass(frozen=True)
class SmilesGrouping:
    """Hasil pengelompokan ligan menurut SMILES.

    Attributes:
        unique_smiles: SMILES yang dikirim/diprediksi, urutan kemunculan pertama.
        index_of: untuk tiap ligan input, indeks SMILES uniknya.
        members: untuk tiap SMILES unik, indeks semua ligan yang memakainya.
    """
    unique_smiles: List[str]
    index_of: List[int]
    members: List[List[int]] = field(default_factory=list)

    @property
    def n_duplicates(self) -> int:
        """Jumlah ligan yang hasilnya berupa salinan (bukan prediksi sendiri)."""
        return len(self.index_of) - len(self.unique_smiles)

    def duplicated_groups(self) -> List[List[int]]:
        return [m for m in self.members if len(m) > 1]


def group_by_smiles(smiles: Sequence[str], names: Optional[Sequence[str]] = None) -> SmilesGrouping:
    """Kelompokkan ligan yang SMILES-nya sama.

    Args:
        smiles: SMILES tiap ligan sesuai urutan input.
        names: nama tiap ligan, dipakai sebagai kunci cadangan bila SMILES kosong.
    """
    names = list(names) if names is not None else [""] * len(smiles)
    seen: Dict[str, int] = {}
    unique: List[str] = []
    members: List[List[int]] = []
    index_of: List[int] = []
    for position, (text, name) in enumerate(zip(smiles, names)):
        key = canonical_key(text, name)
        slot = seen.get(key)
        if slot is None:
            slot = len(unique)
            seen[key] = slot
            unique.append(text or "")
            members.append([])
        members[slot].append(position)
        index_of.append(slot)
    return SmilesGrouping(unique_smiles=unique, index_of=index_of, members=members)


def fan_out(
    unique_rows: Sequence[Optional[Dict[str, Any]]],
    grouping: SmilesGrouping,
    names: Sequence[str],
    groups: Optional[Sequence[Optional[str]]] = None,
) -> List[Dict[str, Any]]:
    """Salin baris ADMET tiap SMILES unik ke semua ligan yang memakainya.

    Args:
        unique_rows: satu baris (dict) per SMILES unik, ``None`` bila tak ada hasil.
        grouping: hasil ``group_by_smiles``.
        names: nama ligan (urutan input).
        groups: grup ligan (urutan input), diisikan ke kolom ``group``.

    Returns:
        Satu dict per ligan yang punya hasil, berurutan seperti input:
        ``ligand`` (+ ``group``) diikuti kolom ADMET.
    """
    rows: List[Dict[str, Any]] = []
    for position, name in enumerate(names):
        source = unique_rows[grouping.index_of[position]]
        if source is None:
            continue
        record: Dict[str, Any] = {"ligand": name}
        if groups is not None:
            record["group"] = groups[position] or ""
        record.update({k: v for k, v in source.items() if k not in ("ligand", "group")})
        rows.append(record)
    return rows


def describe_duplicates(grouping: SmilesGrouping, names: Sequence[str],
                        groups: Optional[Sequence[Optional[str]]] = None, limit: int = 5) -> List[str]:
    """Baris log ramah pembaca untuk senyawa kembar, mis. ``Aspirin (grup: G1, G2)``."""
    lines: List[str] = []
    for members in grouping.duplicated_groups()[:limit]:
        label = names[members[0]]
        if groups is not None:
            label += f" (grup: {', '.join((groups[i] or 'tanpa grup') for i in members)})"
        else:
            label += f" ({len(members)} salinan)"
        lines.append(label)
    remaining = len(grouping.duplicated_groups()) - limit
    if remaining > 0:
        lines.append(f"... dan {remaining} senyawa lain")
    return lines
