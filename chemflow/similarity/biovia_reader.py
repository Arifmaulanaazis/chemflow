"""
Pembaca file Excel hasil export interaksi ligan-reseptor dari BIOVIA
Discovery Studio Visualizer.

Format export BIOVIA bersifat POSISIONAL (tanpa header baku) dengan urutan
kolom: Name, Rendered, Color, Style, ID, Category, Type/Subtype, From,
From Chemistry, To, To Chemistry, lalu opsional Distance/Angle di kolom
berikutnya. Kolom sampai "To Chemistry" (indeks 0-10, 11 kolom) DIJAMIN
selalu ada; kolom setelah itu tidak diandalkan sama sekali di sini karena
BIOVIA kadang tidak menampilkannya.

Setiap baris merepresentasikan satu interaksi antara dua atom, ditulis
sebagai spek posisi "Chain:RESNAME+RESNUM:ATOMNAME" (mis. "A:SER195:OG"),
diparse lewat regex pada kolom From/To.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

_MIN_COLUMNS = 11  # Name..To Chemistry (indeks 0-10)

_ATOM_SPEC_RE = re.compile(
    r"^\s*(?P<chain>[A-Za-z0-9]{1,2}):(?P<resname>[A-Za-z0-9]{1,4}?)(?P<resnum>-?\d+):(?P<atom>.+?)\s*$"
)


@dataclass
class AtomSpec:
    """Satu sisi interaksi (hasil parse "Chain:RESNAME+RESNUM:ATOMNAME")."""
    chain: str
    resname: str
    resnum: int
    atom_name: str

    @property
    def residue_key(self) -> tuple:
        return (self.resnum, self.resname)

    @property
    def residue_label(self) -> str:
        return f"{self.resnum}-{self.resname.title()}"


@dataclass
class BiovaInteraction:
    """Satu baris interaksi dari export BIOVIA (kolom sampai To Chemistry)."""
    category: str
    type_subtype: str
    from_spec: AtomSpec
    from_chemistry: str
    to_spec: AtomSpec
    to_chemistry: str


def parse_atom_spec(raw: object) -> AtomSpec:
    """Parse spek atom BIOVIA "Chain:RESNAME+RESNUM:ATOMNAME".

    Raises:
        ValueError: format tidak cocok pola yang diharapkan.
    """
    text = str(raw or "").strip()
    match = _ATOM_SPEC_RE.match(text)
    if not match:
        raise ValueError(f"Format spek atom BIOVIA tidak dikenali: {raw!r}")
    return AtomSpec(
        chain=match.group("chain"), resname=match.group("resname").upper(),
        resnum=int(match.group("resnum")), atom_name=match.group("atom"),
    )


def read_biovia_interactions(path: "str | Path") -> List[BiovaInteraction]:
    """Baca file Excel export interaksi BIOVIA Discovery Studio.

    Toleran terhadap kolom trailing (Distance/Angle/ID tambahan) yang
    hilang/variabel, karena hanya 11 kolom pertama (Name..To Chemistry)
    yang dibaca. Baris pertama dianggap header (dilewati) hanya jika
    kolom From/To-nya TIDAK cocok pola spek atom BIOVIA; jika cocok,
    seluruh baris (termasuk baris pertama) dianggap data.

    Args:
        path: path file .xlsx export BIOVIA.

    Returns:
        Daftar ``BiovaInteraction``, satu per baris data.

    Raises:
        FileNotFoundError: file tidak ditemukan.
        ValueError: kolom wajib (sampai "To Chemistry") tidak lengkap di
            baris tertentu, atau spek atom From/To tidak bisa diparse
            (pesan menyebut nama file & nomor baris untuk debugging).
    """
    from openpyxl import load_workbook

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File interaksi BIOVIA tidak ditemukan: {path}")

    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]

    rows = [list(row) for row in ws.iter_rows(values_only=True) if any(c is not None for c in row)]
    wb.close()

    if not rows:
        raise ValueError(f"File interaksi BIOVIA kosong: {path}")

    start = 0
    if len(rows) > 1 and not _looks_like_data_row(rows[0]):
        start = 1  # baris pertama header, lewati (hanya jika ada baris data lain setelahnya)

    interactions: List[BiovaInteraction] = []
    for row_idx, row in enumerate(rows[start:], start=start + 1):
        if len(row) < _MIN_COLUMNS:
            raise ValueError(
                f"Baris {row_idx} di '{path.name}' hanya punya {len(row)} kolom, minimal {_MIN_COLUMNS} "
                f"(Name..To Chemistry) diperlukan. Pastikan file adalah export BIOVIA Discovery Studio yang valid."
            )
        try:
            from_spec = parse_atom_spec(row[7])
            to_spec = parse_atom_spec(row[9])
        except ValueError as exc:
            raise ValueError(f"Baris {row_idx} di '{path.name}': {exc}") from exc

        interactions.append(BiovaInteraction(
            category=str(row[5] or ""), type_subtype=str(row[6] or ""),
            from_spec=from_spec, from_chemistry=str(row[8] or ""),
            to_spec=to_spec, to_chemistry=str(row[10] or ""),
        ))

    return interactions


def _looks_like_data_row(row) -> bool:
    if len(row) < _MIN_COLUMNS:
        return False
    try:
        parse_atom_spec(row[7])
        parse_atom_spec(row[9])
        return True
    except ValueError:
        return False


@dataclass
class ProteinLigandContact:
    """Satu kontak protein-ligan (sisi protein + tipe interaksi)."""
    resnum: int
    resname: str
    interaction_type: str

    @property
    def residue_key(self) -> tuple:
        return (self.resnum, self.resname)

    @property
    def residue_label(self) -> str:
        return f"{self.resnum}-{self.resname.title()}"


def filter_protein_ligand(interactions: List[BiovaInteraction], ligand_chain: str) -> List[ProteinLigandContact]:
    """Saring interaksi murni protein-ligan (buang intra-ligand & intra-protein).

    Args:
        interactions: hasil ``read_biovia_interactions()``.
        ligand_chain: chain ID ligan (dari metadata sidecar merge, mis. "X").

    Returns:
        Daftar ``ProteinLigandContact``, sisi protein saja (chain != ligand_chain).
    """
    contacts: List[ProteinLigandContact] = []
    for it in interactions:
        from_is_ligand = it.from_spec.chain == ligand_chain
        to_is_ligand = it.to_spec.chain == ligand_chain
        if from_is_ligand == to_is_ligand:
            continue  # keduanya ligan (intra-ligand) atau keduanya protein (intra-protein)

        protein_spec = it.to_spec if from_is_ligand else it.from_spec
        contacts.append(ProteinLigandContact(
            resnum=protein_spec.resnum, resname=protein_spec.resname, interaction_type=it.type_subtype,
        ))
    return contacts
