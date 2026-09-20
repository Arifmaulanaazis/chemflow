"""
Penetapan muatan parsial gaya Kollman united-atom untuk reseptor protein.

Sumber data:
  - Muatan BACKBONE (N, H amida, CA, HA, C karbonil, O karbonil) memakai
    nilai force field AMBER ff99SB yang terpublikasi luas (Cornell et al.
    1995, *JACS* 117:5179; Hornak et al. 2006, *Proteins* 65:712): N=-0.4157,
    H=+0.2719, CA=+0.0337, HA=+0.0823, C=+0.5973, O=-0.5679. Nilai ini
    identik di hampir semua residu standar.
  - Muatan SIDECHAIN untuk residu bermuatan/polar kunci (ASP/GLU
    karboksilat, LYS/ARG amina bermuatan, CYS tiol/disulfida, HIS dengan
    deteksi status protonasi) memakai nilai representatif dari famili
    force field AMBER. Untuk kebutuhan yang butuh presisi AMBER penuh,
    ganti tabel ini dengan file parameter force field terverifikasi
    (mis. lewat AmberTools/ParmEd).
  - AutoDock Vina tidak memakai elektrostatika Coulombic eksplisit pada
    scoring function-nya. Ia memakai fungsi empiris berbasis tipe atom
    (hidrofobik, H-bond geometris, dsb), sehingga ketidaklengkapan tabel
    muatan reseptor di sini tidak berdampak besar pada hasil docking.

Atom/residu yang tak ada di tabel: fallback default adalah muatan ``0.0``,
selalu dicatat ke logger supaya pengguna tahu atom mana yang tak tercover
tabel. Fallback alternatif ``"gasteiger"`` tersedia untuk pengguna yang
lebih mengutamakan akurasi fisik per-atom (dihitung RDKit).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional, Tuple

FallbackMode = Literal["zero", "gasteiger"]

# Muatan backbone AMBER ff99SB (identik untuk semua residu standar)
_BACKBONE_CHARGES: Dict[str, float] = {
    "N": -0.4157,
    "H": 0.2719,    # H amida pada N backbone (tidak ada pada PRO)
    "CA": 0.0337,
    "HA": 0.0823,
    "C": 0.5973,
    "O": -0.5679,
}

# Koreksi terminus rantai (pendekatan sederhana, bukan nilai AMBER presisi
#     tinggi). N-terminus NH3+ & C-terminus COO- membawa muatan ekstra
# dibanding residu di tengah rantai.
_N_TERMINUS_EXTRA: Dict[str, float] = {"H1": 0.1921, "H2": 0.1921, "H3": 0.1921}
_C_TERMINUS_EXTRA: Dict[str, float] = {"OXT": -0.5679}  # OXT dapat porsi sama dgn O karbonil

# Muatan sidechain representatif untuk residu bermuatan/polar kunci
_SIDECHAIN_CHARGES: Dict[str, Dict[str, float]] = {
    "ASP": {"CG": 0.7994, "OD1": -0.8014, "OD2": -0.8014},
    "GLU": {"CD": 0.8054, "OE1": -0.8188, "OE2": -0.8188},
    "LYS": {"NZ": -0.3854, "HZ1": 0.3400, "HZ2": 0.3400, "HZ3": 0.3400},
    "ARG": {
        "NE": -0.5295, "HE": 0.3456,
        "CZ": 0.8076,
        "NH1": -0.8627, "HH11": 0.4478, "HH12": 0.4478,
        "NH2": -0.8627, "HH21": 0.4478, "HH22": 0.4478,
    },
    "CYS": {"SG": -0.1996},        # sistein bebas (tiol, HG hadir)
    "CYX": {"SG": -0.0984},        # sistein disulfida (HG tidak ada)
    "HID": {"ND1": -0.3819, "CE1": 0.2057, "NE2": -0.5727, "HD1": 0.3652},
    "HIE": {"ND1": -0.5432, "CE1": 0.1868, "NE2": -0.2795, "HE2": 0.3324},
    "HIP": {"ND1": -0.1739, "CE1": -0.0170, "NE2": -0.1717, "HD1": 0.3800, "HE2": 0.3900},
}


class KollmanChargeAssigner:
    """Menetapkan muatan parsial gaya-Kollman ke setiap atom reseptor RDKit Mol."""

    def __init__(self, fallback_mode: FallbackMode = "zero", logger: Optional[logging.Logger] = None) -> None:
        self._fallback_mode = fallback_mode
        self._log = logger or logging.getLogger(__name__)

    def assign(self, mol: Any) -> Dict[int, float]:
        """Tetapkan muatan untuk setiap atom dalam ``mol`` berdasar residu+nama atom.

        Muatan disimpan sebagai property RDKit ``_KollmanCharge`` pada tiap
        atom (float) sekaligus dikembalikan sebagai dict ``{atom_idx: charge}``.

        Args:
            mol: RDKit Mol reseptor (harus punya ``PDBResidueInfo`` per atom,
                hasil ``Chem.MolFromPDBFile``).

        Returns:
            Pemetaan indeks atom -> muatan yang ditetapkan.
        """
        charges: Dict[int, float] = {}
        fallback_gasteiger: Optional[Dict[int, float]] = None
        if self._fallback_mode == "gasteiger":
            fallback_gasteiger = self._compute_gasteiger_fallback(mol)

        residue_atoms = self._group_by_residue(mol)

        for (chain, resnum), atom_indices in residue_atoms.items():
            names = {idx: self._atom_name(mol, idx) for idx in atom_indices}
            resname_raw = self._residue_name(mol, atom_indices[0])
            resname = self._resolve_protonation_variant(resname_raw, names)

            is_first = self._is_chain_terminus(mol, atom_indices, residue_atoms, chain, resnum, first=True)
            is_last = self._is_chain_terminus(mol, atom_indices, residue_atoms, chain, resnum, first=False)

            for idx in atom_indices:
                atom_name = names[idx]
                q = self._lookup(resname, atom_name)
                if q is None and is_first:
                    q = _N_TERMINUS_EXTRA.get(atom_name)
                if q is None and is_last:
                    q = _C_TERMINUS_EXTRA.get(atom_name)

                if q is None:
                    if fallback_gasteiger is not None:
                        q = fallback_gasteiger.get(idx, 0.0)
                    else:
                        q = 0.0
                        self._log.debug(
                            f"[Kollman] Residu {resname_raw} {chain}{resnum} atom '{atom_name}' "
                            f"tidak ada di tabel, fallback charge=0.0."
                        )

                charges[idx] = q
                mol.GetAtomWithIdx(idx).SetDoubleProp("_KollmanCharge", q)

        n_fallback = sum(
            1 for idx in charges
            if self._lookup(
                self._resolve_protonation_variant(self._residue_name(mol, idx), {}),
                self._atom_name(mol, idx),
            ) is None
        )
        if n_fallback and self._fallback_mode == "zero":
            self._log.info(
                f"[Kollman] {n_fallback} atom memakai fallback charge=0.0 "
                f"(residu nonstandar/atom di luar tabel kurasi, lihat DEBUG log untuk detail per-atom)."
            )

        return charges


    def _lookup(self, resname: str, atom_name: str) -> Optional[float]:
        if atom_name in _BACKBONE_CHARGES and not (resname == "PRO" and atom_name == "H"):
            return _BACKBONE_CHARGES[atom_name]
        sidechain = _SIDECHAIN_CHARGES.get(resname)
        if sidechain and atom_name in sidechain:
            return sidechain[atom_name]
        if resname in ("HOH", "WAT") and atom_name in ("O", "OW"):
            return -0.834
        if resname in ("HOH", "WAT") and atom_name in ("H1", "H2", "HW1", "HW2"):
            return 0.417
        return None

    def _resolve_protonation_variant(self, resname: str, atom_names: Dict[int, str]) -> str:
        """Pilih varian protonasi His (HID/HIE/HIP) atau Cys (CYS/CYX)
        berdasar keberadaan atom H tertentu. Inferensi struktural, bukan
        nama residu literal di file PDB yang seringkali cuma "HIS"/"CYS"."""
        names = set(atom_names.values())
        if resname == "HIS":
            has_hd1 = "HD1" in names
            has_he2 = "HE2" in names
            if has_hd1 and has_he2:
                return "HIP"
            if has_hd1:
                return "HID"
            if has_he2:
                return "HIE"
            return "HIE"
        if resname == "CYS":
            return "CYS" if "HG" in names else "CYX"
        return resname

    def _group_by_residue(self, mol: Any) -> Dict[Tuple[str, int], list]:
        groups: Dict[Tuple[str, int], list] = {}
        for atom in mol.GetAtoms():
            info = atom.GetPDBResidueInfo()
            if info is None:
                continue
            key = (info.GetChainId(), info.GetResidueNumber())
            groups.setdefault(key, []).append(atom.GetIdx())
        return groups

    def _atom_name(self, mol: Any, idx: int) -> str:
        info = mol.GetAtomWithIdx(idx).GetPDBResidueInfo()
        return (info.GetName() or "").strip().upper() if info else ""

    def _residue_name(self, mol: Any, idx: int) -> str:
        info = mol.GetAtomWithIdx(idx).GetPDBResidueInfo()
        return (info.GetResidueName() or "").strip().upper() if info else ""

    def _is_chain_terminus(self, mol: Any, atom_indices: list, residue_atoms: Dict, chain: str,
                            resnum: int, first: bool) -> bool:
        same_chain_resnums = sorted({rn for (c, rn) in residue_atoms if c == chain})
        if not same_chain_resnums:
            return False
        return resnum == (same_chain_resnums[0] if first else same_chain_resnums[-1])

    def _compute_gasteiger_fallback(self, mol: Any) -> Dict[int, float]:
        from rdkit.Chem import AllChem
        try:
            AllChem.ComputeGasteigerCharges(mol)
        except Exception:
            return {}
        result = {}
        for atom in mol.GetAtoms():
            if atom.HasProp("_GasteigerCharge"):
                try:
                    result[atom.GetIdx()] = float(atom.GetProp("_GasteigerCharge"))
                except ValueError:
                    result[atom.GetIdx()] = 0.0
        return result
