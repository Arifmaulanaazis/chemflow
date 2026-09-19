"""
Pembaca file PDBQT multi-pose hasil AutoDock Vina, dikonversi ke RDKit Mol.

PDBQT bukan format yang dipahami langsung oleh ``Chem.MolFromPDBFile`` RDKit
(kolom charge & tipe-atom AutoDock di ujung baris tidak standar PDB), jadi
tiap baris ATOM/HETATM dikonversi manual menjadi blok PDB murni sebelum
diparse RDKit.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# Pemetaan tipe atom AutoDock -> elemen PDB, dipakai sebagai fallback
# ketika kolom elemen PDB standar tidak bisa ditebak dari nama atom.
_AD_TYPE_TO_ELEMENT: Dict[str, str] = {
    "hd": "H", "h": "H", "c": "C", "a": "C", "n": "N", "na": "N",
    "nb": "N", "oa": "O", "ob": "O", "sa": "S", "sb": "S", "s": "S",
    "f": "F", "cl": "Cl", "br": "Br", "i": "I", "p": "P",
    "zn": "Zn", "mg": "Mg", "ca": "Ca", "mn": "Mn", "fe": "Fe", "cu": "Cu",
}


def read_pdbqt(pdbqt_path: Path, logger: Optional[logging.Logger] = None) -> List[Any]:
    """Baca semua pose (MODEL...ENDMDL) dari file PDBQT hasil Vina.

    Args:
        pdbqt_path: path file .pdbqt multi-pose.
        logger: logger opsional.

    Returns:
        Daftar RDKit ``Mol``, urutan sesuai urutan MODEL di file (mode 1 =
        pose afinitas terbaik menurut Vina, selalu elemen pertama list).
        List kosong jika file tak terbaca sama sekali (tidak raise).
    """
    from rdkit import Chem  # type: ignore

    log = logger or logging.getLogger(__name__)
    try:
        text = pdbqt_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        log.warning(f"Tidak bisa membaca {pdbqt_path}: {exc}")
        return []

    blocks: List[List[str]] = []
    current: List[str] = []
    in_model = False
    for line in text.splitlines():
        if line.startswith("MODEL"):
            in_model = True
            current = []
            continue
        if line.startswith("ENDMDL"):
            in_model = False
            if current:
                blocks.append(current)
            continue
        if in_model and line.startswith(("ATOM", "HETATM")):
            current.append(line)

    mols: List[Any] = []
    if blocks:
        for block in blocks:
            pdb_block = _atoms_to_pdb_block(block)
            mol = Chem.MolFromPDBBlock(pdb_block, sanitize=False, removeHs=False)
            if mol is not None:
                try:
                    Chem.SanitizeMol(mol, catchErrors=True)
                except Exception:
                    pass
                mols.append(mol)
    else:
        # Tak ada blok MODEL sama sekali, coba sebagai file PDB/PDBQT satu-pose.
        mol = Chem.MolFromPDBFile(str(pdbqt_path), sanitize=False, removeHs=False)
        if mol is not None:
            try:
                Chem.SanitizeMol(mol, catchErrors=True)
            except Exception:
                pass
            mols.append(mol)

    if not mols:
        log.warning(f"Tidak ada pose terbaca dari {pdbqt_path.name}")
    return mols


def _atoms_to_pdb_block(lines: List[str]) -> str:
    """Konversi baris ATOM/HETATM bergaya PDBQT ke blok PDB standar minimal."""
    out: List[str] = []
    for line in lines:
        record = line[:6]
        serial = line[6:11]
        atom_name = line[12:16]
        alt = line[16:17]
        resname = line[17:20] if len(line) > 20 else "LIG"
        chain = line[21:22] if len(line) > 22 else "L"
        resnum = line[22:26] if len(line) > 26 else "   1"
        x = line[30:38]
        y = line[38:46]
        z = line[46:54]
        occ = line[54:60] if len(line) >= 60 else "  1.00"
        temp = line[60:66] if len(line) >= 66 else "  0.00"

        ad_type = line[77:].strip().split()[-1] if len(line) > 77 and line[77:].strip() else ""
        element = _guess_element(atom_name.strip(), ad_type)

        pdb_line = (
            f"{record:<6}{serial:>5} {atom_name:<4}{alt:1}{resname:>3} {chain:1}{resnum:>4}    "
            f"{x:>8}{y:>8}{z:>8}{occ:>6}{temp:>6}          {element:>2}\n"
        )
        out.append(pdb_line)
    return "".join(out) + "END\n"


def _guess_element(atom_name: str, ad_type: str) -> str:
    """Tebak elemen dari nama atom PDBQT / tipe AutoDock, fallback 'C'."""
    if ad_type:
        key = ad_type.lower().rstrip("+-")
        if key in _AD_TYPE_TO_ELEMENT:
            return _AD_TYPE_TO_ELEMENT[key]
    if len(atom_name) >= 2 and atom_name[0].isalpha() and atom_name[1].islower():
        return atom_name[:2].capitalize()
    if atom_name:
        return atom_name[0].upper()
    return "C"
