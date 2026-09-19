"""
Penentuan tipe atom AutoDock4 (kolom terakhir PDBQT) untuk atom reseptor,
berbasis kalkulasi RDKit (aromatisitas, valensi, ikatan rangkap).

Aturan tipe (mengikuti format publik AutoDock4: Morris et al. 2009,
J. Comput. Chem., dan AutoDock User Guide):
    H  -> "HD" (donor, tetangga bukan karbon: N/O/S) atau "H" (nonpolar)
    C  -> "A"  (karbon aromatik, via ``atom.GetIsAromatic()`` RDKit) atau "C"
    N  -> "NA" (akseptor: N nonaromatik dgn lone pair bebas, bukan amida)
          atau "N" (netral, mis. N amida planar)
    O  -> selalu "OA" (akseptor)
    S  -> "SA" (akseptor) kecuali sulfoksida/sulfon (>=1 ikatan rangkap ke O)
          -> tetap "S"
"""

from __future__ import annotations

from typing import Any, Dict


class AD4AtomTyper:
    """Menentukan tipe atom AutoDock4 untuk tiap atom sebuah RDKit Mol."""

    def assign(self, mol: Any) -> Dict[int, str]:
        """Tetapkan tipe AD4 ke setiap atom, disimpan sbg property ``_AD4Type``.

        Args:
            mol: RDKit Mol (sudah disanitasi, aromatisitas RDKit valid).

        Returns:
            Pemetaan indeks atom -> string tipe AutoDock4.
        """
        types: Dict[int, str] = {}
        for atom in mol.GetAtoms():
            t = self._type_for(atom)
            types[atom.GetIdx()] = t
            atom.SetProp("_AD4Type", t)
        return types

    def _type_for(self, atom: Any) -> str:
        z = atom.GetAtomicNum()
        symbol = atom.GetSymbol()

        if z == 1:
            neighbors = atom.GetNeighbors()
            if neighbors and neighbors[0].GetAtomicNum() not in (6,):
                return "HD"
            return "H"

        if z == 6:
            return "A" if atom.GetIsAromatic() else "C"

        if z == 7:
            if atom.GetIsAromatic():
                return "NA"
            is_amide_like = any(
                nbr.GetAtomicNum() == 6 and self._is_carbonyl_carbon(nbr)
                for nbr in atom.GetNeighbors()
            )
            return "N" if is_amide_like else "NA"

        if z == 8:
            return "OA"

        if z == 16:
            n_double_to_o = sum(
                1 for bond in atom.GetBonds()
                if bond.GetBondTypeAsDouble() == 2.0
                and (bond.GetBeginAtom().GetAtomicNum() == 8 or bond.GetEndAtom().GetAtomicNum() == 8)
            )
            return "S" if n_double_to_o >= 1 else "SA"

        # Elemen lain: pakai simbol apa adanya (halogen, logam, dst, sudah
        # sesuai konvensi AutoDock untuk elemen non-organik umum).
        return symbol

    @staticmethod
    def _is_carbonyl_carbon(carbon_atom: Any) -> bool:
        """True jika atom karbon ini punya ikatan rangkap ke oksigen (C=O),
        indikasi kuat bahwa N tetangganya adalah nitrogen amida (planar,
        bukan akseptor H-bond klasik)."""
        for bond in carbon_atom.GetBonds():
            if bond.GetBondTypeAsDouble() != 2.0:
                continue
            other = bond.GetOtherAtom(carbon_atom)
            if other.GetAtomicNum() == 8:
                return True
        return False
