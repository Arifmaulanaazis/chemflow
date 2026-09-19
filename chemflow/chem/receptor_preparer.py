"""
Preparasi reseptor protein. Dua jalur keluaran yang SENGAJA dipisah total:

  - ``prepare_for_docking()``: hidrogen polar-only + muatan Kollman + tipe
    atom AD4 -> PDBQT rigid, dipakai Vina.
  - ``prepare_for_merge()``: reseptor BERSIH (tanpa H, tanpa muatan) -> PDB
    polos, dipakai HANYA untuk menggabungkan pose terbaik + reseptor saat
    visualisasi kompleks (``docking/merge.py``). Reseptor versi docking
    (sudah ada H & muatan) TIDAK BOLEH dipakai untuk merge, karena itu akan
    membuat file kompleks berisi H/muatan tambahan yang tidak semestinya
    ditampilkan sebagai struktur "asli" ke pengguna.

Residu HETATM yang struktural bagian dari backbone protein (asam amino
termodifikasi, mis. MSE) SELALU dipertahankan lewat pengecekan
``is_polymer_backbone_complete``, bukan daftar nama hardcode, supaya
tidak ikut terhapus walau ``remove_hetero_ligands=True``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Set

from chemflow.chem.atom_typing import AD4AtomTyper
from chemflow.chem.kollman_charges import FallbackMode, KollmanChargeAssigner
from chemflow.chem.pdbqt_writer import ReceptorPDBQTWriter
from chemflow.utils.residue_backbone import is_polymer_backbone_complete

_NUC_RES = {"DA", "DC", "DG", "DT", "DU", "A", "C", "G", "T", "U"}
_METALS = {"ZN", "MG", "FE", "MN", "CU", "CO", "NI", "CA", "NA", "K", "CD", "HG"}
_WATERS = {"HOH", "WAT"}


class ReceptorPreparer:
    """Preparasi reseptor: pembersihan, hidrogenasi polar, muatan Kollman, PDBQT/PDB."""

    def __init__(self, kollman_fallback: FallbackMode = "zero", logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger(__name__)
        self._kollman = KollmanChargeAssigner(fallback_mode=kollman_fallback, logger=self._log)
        self._typer = AD4AtomTyper()
        self._writer = ReceptorPDBQTWriter()

    def load(self, pdb_path: Path) -> Any:
        """Baca file PDB menjadi RDKit Mol (semua atom & residue-info utuh).

        Args:
            pdb_path: path file .pdb reseptor (sudah diunduh dari RCSB).

        Returns:
            RDKit ``Mol``.

        Raises:
            ValueError: file gagal diparse RDKit sama sekali.
        """
        from rdkit import Chem

        mol = Chem.MolFromPDBFile(str(pdb_path), sanitize=False, removeHs=False, proximityBonding=True)
        if mol is None:
            raise ValueError(f"Gagal memparse file PDB: {pdb_path}")
        try:
            Chem.SanitizeMol(mol, catchErrors=True)
        except Exception:
            pass
        self._log.debug(f"Reseptor dimuat: {mol.GetNumAtoms()} atom dari {pdb_path.name}")
        return mol

    def prepare_for_docking(
        self,
        mol: Any,
        output_pdbqt: Path,
        *,
        remove_waters: bool = True,
        remove_hetero_ligands: bool = True,
        keep_metals: bool = True,
    ) -> Path:
        """Siapkan reseptor untuk docking Vina: bersihkan -> H polar-only ->
        muatan Kollman -> tipe AD4 -> tulis PDBQT rigid.

        Returns:
            Path file .pdbqt yang ditulis.
        """
        m = self._clean(mol, remove_waters, remove_hetero_ligands, keep_metals)
        m = self._add_polar_hydrogens_only(m)
        self._kollman.assign(m)
        self._typer.assign(m)
        return self._writer.write(m, output_pdbqt)

    def prepare_for_merge(
        self,
        mol: Any,
        output_pdb: Path,
        *,
        remove_waters: bool = True,
        remove_hetero_ligands: bool = True,
        keep_metals: bool = True,
    ) -> Path:
        """Siapkan reseptor BERSIH (tanpa H, tanpa muatan) untuk penggabungan
        kompleks (``docking/merge.py``).

        Returns:
            Path file .pdb yang ditulis.
        """
        from rdkit import Chem

        m = self._clean(mol, remove_waters, remove_hetero_ligands, keep_metals)

        rw = Chem.RWMol(m)
        h_indices = [a.GetIdx() for a in rw.GetAtoms() if a.GetAtomicNum() == 1]
        for idx in sorted(h_indices, reverse=True):
            rw.RemoveAtom(idx)
        m = rw.GetMol()

        for atom in m.GetAtoms():
            atom.SetFormalCharge(0)
            for prop in ("_GasteigerCharge", "_TriposPartialCharge", "_KollmanCharge"):
                if atom.HasProp(prop):
                    atom.ClearProp(prop)

        try:
            Chem.SanitizeMol(m, catchErrors=True)
        except Exception:
            pass

        output_pdb.parent.mkdir(parents=True, exist_ok=True)
        try:
            Chem.MolToPDBFile(m, str(output_pdb))
        except Exception as exc:
            self._log.info(
                f"Penulisan {output_pdb.name} gagal ({exc}), diulang tanpa penanda aromatik "
                f"(berkas PDB polos tidak memerlukannya)."
            )
            block = Chem.MolToPDBBlock(self._drop_aromaticity(m)) or ""
            output_pdb.write_text(block, encoding="utf-8")

        self._log.debug(f"Reseptor bersih (utk merge) ditulis: {output_pdb.name} ({m.GetNumAtoms()} atom)")
        return output_pdb

    @staticmethod
    def _drop_aromaticity(mol: Any) -> Any:
        """Salinan ``mol`` tanpa penanda aromatik. Setelah semua H dibuang, cincin
        aromatik yang semula memuat NH (mis. imidazol HIS netral yang hanya ber-HE2)
        tidak bisa di-kekulize, padahal PDB polos tidak membutuhkan aromatisitas."""
        from rdkit import Chem

        rw = Chem.RWMol(mol)
        for atom in rw.GetAtoms():
            atom.SetIsAromatic(False)
        for bond in rw.GetBonds():
            bond.SetIsAromatic(False)
            if bond.GetBondType() == Chem.BondType.AROMATIC:
                bond.SetBondType(Chem.BondType.SINGLE)
        return rw.GetMol()


    def _clean(self, mol: Any, remove_waters: bool, remove_hetero_ligands: bool, keep_metals: bool) -> Any:
        """Buang air & HETATM ligan asli, PERTAHANKAN residu nonstandar yang
        secara struktural bagian dari backbone protein (mis. MSE)."""
        from rdkit import Chem

        rw = Chem.RWMol(mol)

        residue_atom_elements: dict = {}
        for a in rw.GetAtoms():
            info = a.GetPDBResidueInfo()
            if info is None:
                continue
            key = (info.GetChainId(), info.GetResidueNumber())
            name = (info.GetName() or "").strip().upper()
            if name:
                residue_atom_elements.setdefault(key, {})[name] = a.GetSymbol().upper()

        backbone_complete: Set = {
            key for key, elems in residue_atom_elements.items()
            if is_polymer_backbone_complete(elems)
        }

        to_delete = []
        preserved = []
        preserved_keys: Set = set()
        for a in rw.GetAtoms():
            info = a.GetPDBResidueInfo()
            if info is None:
                continue
            resname = (info.GetResidueName() or "").strip().upper()
            is_het = bool(info.GetIsHeteroAtom())

            if remove_waters and resname in _WATERS:
                to_delete.append(a.GetIdx())
                continue
            if remove_hetero_ligands and is_het:
                sym = a.GetSymbol().upper()
                if keep_metals and sym in _METALS:
                    continue
                key = (info.GetChainId(), info.GetResidueNumber())
                if key in backbone_complete:
                    if key not in preserved_keys:
                        preserved_keys.add(key)
                        preserved.append(f"{resname} {key[0]}{key[1]}")
                    continue
                to_delete.append(a.GetIdx())

        if preserved:
            self._log.info(
                f"Mempertahankan {len(preserved)} residu nonstandar sbg bagian rantai protein: "
                f"{', '.join(preserved)}"
            )

        for idx in sorted(set(to_delete), reverse=True):
            rw.RemoveAtom(int(idx))
        return rw.GetMol()

    def _add_polar_hydrogens_only(self, mol: Any) -> Any:
        """Tambah H penuh (dengan residue-info), lalu buang H yang nempel
        ke atom C (nonpolar). Hanya H polar (nempel N/O/S, tipe HD) yang
        dipertahankan untuk docking."""
        from rdkit import Chem

        m = Chem.AddHs(mol, addCoords=True)
        for atom in m.GetAtoms():
            if atom.GetAtomicNum() == 1 and atom.GetPDBResidueInfo() is None:
                neighbors = atom.GetNeighbors()
                if not neighbors:
                    continue
                neighbor_info = neighbors[0].GetPDBResidueInfo()
                if neighbor_info:
                    new_info = Chem.AtomPDBResidueInfo()
                    new_info.SetChainId(neighbor_info.GetChainId())
                    new_info.SetResidueName(neighbor_info.GetResidueName())
                    new_info.SetResidueNumber(neighbor_info.GetResidueNumber())
                    new_info.SetIsHeteroAtom(neighbor_info.GetIsHeteroAtom())
                    new_info.SetName(" H  ")
                    atom.SetPDBResidueInfo(new_info)

        rw = Chem.RWMol(m)
        nonpolar_h = [
            a.GetIdx() for a in rw.GetAtoms()
            if a.GetAtomicNum() == 1 and a.GetNeighbors() and a.GetNeighbors()[0].GetAtomicNum() == 6
        ]
        for idx in sorted(nonpolar_h, reverse=True):
            rw.RemoveAtom(idx)
        return rw.GetMol()
