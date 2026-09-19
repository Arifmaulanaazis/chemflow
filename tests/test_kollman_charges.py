"""Test KollmanChargeAssigner: lookup backbone, fallback, disambiguasi His/Cys."""

import pytest

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem

from chemflow.chem.kollman_charges import KollmanChargeAssigner


def _make_atom_mol(entries):
    """Bangun RDKit Mol sederhana dari daftar (element, resname, resnum, chain, atom_name)."""
    mol = Chem.RWMol()
    conf_coords = []
    for i, (elem, resname, resnum, chain, atom_name, is_hetero) in enumerate(entries):
        atom = Chem.Atom(elem)
        idx = mol.AddAtom(atom)
        info = Chem.AtomPDBResidueInfo()
        info.SetChainId(chain)
        info.SetResidueName(resname)
        info.SetResidueNumber(resnum)
        info.SetIsHeteroAtom(is_hetero)
        info.SetName(f" {atom_name:<3}")
        mol.GetAtomWithIdx(idx).SetPDBResidueInfo(info)
        conf_coords.append((float(i), 0.0, 0.0))

    m = mol.GetMol()
    conf = Chem.Conformer(m.GetNumAtoms())
    for i, (x, y, z) in enumerate(conf_coords):
        conf.SetAtomPosition(i, (x, y, z))
    m.AddConformer(conf, assignId=True)
    return m


def test_backbone_charge_terpasang():
    mol = _make_atom_mol([
        ("N", "ALA", 1, "A", "N", False),
        ("C", "ALA", 1, "A", "CA", False),
        ("C", "ALA", 1, "A", "C", False),
        ("O", "ALA", 1, "A", "O", False),
    ])
    assigner = KollmanChargeAssigner(fallback_mode="zero")
    charges = assigner.assign(mol)
    assert charges[0] == pytest.approx(-0.4157)
    assert charges[1] == pytest.approx(0.0337)
    assert charges[2] == pytest.approx(0.5973)
    assert charges[3] == pytest.approx(-0.5679)


def test_fallback_zero_untuk_atom_tak_dikenal():
    mol = _make_atom_mol([
        ("C", "XYZ", 1, "A", "ZZZ", True),  # residu & nama atom fiktif, tidak ada di tabel manapun
    ])
    assigner = KollmanChargeAssigner(fallback_mode="zero")
    charges = assigner.assign(mol)
    assert charges[0] == 0.0


def test_fallback_gasteiger_berbeda_dari_nol():
    mol = _make_atom_mol([
        ("C", "XYZ", 1, "A", "ZZZ", True),
        ("O", "XYZ", 1, "A", "ZZO", True),
    ])
    # Ikatan sederhana C-O agar Gasteiger punya sesuatu untuk dihitung.
    rw = Chem.RWMol(mol)
    rw.AddBond(0, 1, Chem.BondType.SINGLE)
    mol2 = rw.GetMol()
    Chem.SanitizeMol(mol2, catchErrors=True)

    assigner = KollmanChargeAssigner(fallback_mode="gasteiger")
    charges = assigner.assign(mol2)
    # Gasteiger pada C-O harus menghasilkan muatan tak-nol yang bertanda berlawanan.
    assert charges[0] != 0.0 or charges[1] != 0.0


def test_disambiguasi_his_hip_saat_kedua_h_hadir():
    mol = _make_atom_mol([
        ("N", "HIS", 1, "A", "ND1", False),
        ("H", "HIS", 1, "A", "HD1", False),
        ("N", "HIS", 1, "A", "NE2", False),
        ("H", "HIS", 1, "A", "HE2", False),
    ])
    assigner = KollmanChargeAssigner(fallback_mode="zero")
    charges = assigner.assign(mol)
    # HIP: ND1 charge sesuai tabel HIP, bukan HID/HIE.
    from chemflow.chem.kollman_charges import _SIDECHAIN_CHARGES
    assert charges[0] == pytest.approx(_SIDECHAIN_CHARGES["HIP"]["ND1"])


def test_disambiguasi_cys_disulfida_tanpa_hg():
    mol = _make_atom_mol([
        ("S", "CYS", 1, "A", "SG", False),
    ])
    assigner = KollmanChargeAssigner(fallback_mode="zero")
    charges = assigner.assign(mol)
    from chemflow.chem.kollman_charges import _SIDECHAIN_CHARGES
    assert charges[0] == pytest.approx(_SIDECHAIN_CHARGES["CYX"]["SG"])
