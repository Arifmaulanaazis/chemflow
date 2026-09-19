"""
Penulis PDBQT reseptor "flat" (tanpa pohon torsi ROOT/BRANCH/TORSDOF,
karena reseptor docking bersifat rigid).

Dipakai alih-alih OpenBabel untuk reseptor supaya muatan Kollman
(``chem/kollman_charges.py``) dan tipe atom AutoDock4
(``chem/atom_typing.py``) yang sudah dihitung TIDAK tertimpa oleh model
muatan Gasteiger bawaan OpenBabel. Kalau konversi lewat obabel, OpenBabel
akan menghitung ulang muatannya sendiri dan mengabaikan nilai Kollman.

Format kolom mengikuti spesifikasi publik PDBQT AutoDock (AutoDock4 User
Guide / format ATOM standar PDB + 2 kolom tambahan AutoDock: muatan parsial
& tipe atom AutoDock).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


class ReceptorPDBQTWriter:
    """Menulis RDKit Mol reseptor (dengan muatan & tipe AD4 sudah di-set
    sebagai atom property) menjadi file PDBQT flat/rigid."""

    def write(self, mol: Any, output_path: Path) -> Path:
        """Tulis reseptor ke PDBQT.

        Args:
            mol: RDKit Mol dengan property ``_KollmanCharge`` (float) dan
                ``_AD4Type`` (str) sudah di-set per atom (lihat
                ``KollmanChargeAssigner``/``AD4AtomTyper``), serta
                ``PDBResidueInfo`` per atom (dari parsing PDB) dan tepat 1
                conformer.

        Returns:
            Path file .pdbqt yang ditulis.

        Raises:
            ValueError: molekul tidak punya conformer.
        """
        if mol.GetNumConformers() == 0:
            raise ValueError("Molekul reseptor tidak punya conformer, tidak bisa menulis koordinat PDBQT.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        conf = mol.GetConformer(0)

        lines = ["REMARK  Reseptor rigid, ditulis oleh chemflow.chem.pdbqt_writer\n"]
        serial = 1
        current_chain: Optional[str] = None

        for atom in mol.GetAtoms():
            info = atom.GetPDBResidueInfo()
            pos = conf.GetAtomPosition(atom.GetIdx())

            atom_name = (info.GetName().strip() if info else atom.GetSymbol())[:4]
            resname = (info.GetResidueName().strip() if info else "UNK")[:3]
            chain = (info.GetChainId().strip() if info else "A") or "A"
            resnum = info.GetResidueNumber() if info else 1
            is_hetero = bool(info.GetIsHeteroAtom()) if info else False
            record = "HETATM" if is_hetero else "ATOM  "

            if current_chain is not None and chain != current_chain:
                lines.append("TER\n")
            current_chain = chain

            charge = atom.GetDoubleProp("_KollmanCharge") if atom.HasProp("_KollmanCharge") else 0.0
            ad_type = atom.GetProp("_AD4Type") if atom.HasProp("_AD4Type") else atom.GetSymbol()

            line = (
                f"{record}{serial:>5} {atom_name:<4}{'':1}{resname:>3} {chain:1}{resnum:>4}{'':1}   "
                f"{pos.x:>8.3f}{pos.y:>8.3f}{pos.z:>8.3f}{1.0:>6.2f}{0.0:>6.2f}    "
                f"{charge:>6.3f} {ad_type:<2}\n"
            )
            lines.append(line)
            serial += 1

        lines.append("TER\n")

        output_path.write_text("".join(lines), encoding="utf-8")
        return output_path
