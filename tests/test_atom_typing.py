"""Test AD4AtomTyper: aturan tipe atom AutoDock4 (H/HD, C/A, N/NA, OA, S/SA)."""

import pytest

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem

from chemflow.chem.atom_typing import AD4AtomTyper


def _typed(smiles):
    mol = Chem.MolFromSmiles(smiles)
    mol = Chem.AddHs(mol)
    Chem.SanitizeMol(mol)
    types = AD4AtomTyper().assign(mol)
    return mol, types


def test_karbon_aromatik_jadi_a_alifatik_jadi_c():
    mol, types = _typed("c1ccccc1C")  # toluena: cincin aromatik + metil alifatik
    aromatic_types = {types[a.GetIdx()] for a in mol.GetAtoms() if a.GetSymbol() == "C" and a.GetIsAromatic()}
    aliphatic_types = {types[a.GetIdx()] for a in mol.GetAtoms() if a.GetSymbol() == "C" and not a.GetIsAromatic()}
    assert aromatic_types == {"A"}
    assert aliphatic_types == {"C"}


def test_hidrogen_polar_hd_vs_nonpolar_h():
    mol, types = _typed("CO")  # metanol: H di C (nonpolar), H di O (polar)
    h_types = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 1:
            h_types.append(types[atom.GetIdx()])
    assert "HD" in h_types  # H-O
    assert "H" in h_types   # H-C


def test_oksigen_selalu_oa():
    mol, types = _typed("CC(=O)O")  # asam asetat: 2 oksigen berbeda konteks
    o_types = {types[a.GetIdx()] for a in mol.GetAtoms() if a.GetSymbol() == "O"}
    assert o_types == {"OA"}


def test_nitrogen_amida_netral_bukan_akseptor():
    mol, types = _typed("CC(=O)N")  # asetamida: N amida (planar, dekat C=O)
    n_atom = next(a for a in mol.GetAtoms() if a.GetSymbol() == "N")
    assert types[n_atom.GetIdx()] == "N"


def test_nitrogen_amina_alifatik_jadi_akseptor_na():
    mol, types = _typed("CCN")  # etilamina: amina alifatik biasa
    n_atom = next(a for a in mol.GetAtoms() if a.GetSymbol() == "N")
    assert types[n_atom.GetIdx()] == "NA"


def test_semua_atom_dapat_property_ad4type():
    mol, types = _typed("CCO")
    for atom in mol.GetAtoms():
        assert atom.HasProp("_AD4Type")
        assert atom.GetProp("_AD4Type") == types[atom.GetIdx()]
