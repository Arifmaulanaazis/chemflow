"""Test ReceptorPDBQTWriter: format kolom, kolom charge & tipe AD4, TER per chain."""

import pytest

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem

from chemflow.chem.pdbqt_writer import ReceptorPDBQTWriter


def _mol_2_chains():
    rw = Chem.RWMol()
    coords = []
    specs = [
        ("N", "ALA", 1, "A", "N", -0.4157, "NA"),
        ("C", "ALA", 1, "A", "CA", 0.0337, "C"),
        ("N", "GLY", 1, "B", "N", -0.4157, "NA"),
    ]
    for i, (elem, resname, resnum, chain, name, charge, ad4) in enumerate(specs):
        idx = rw.AddAtom(Chem.Atom(elem))
        info = Chem.AtomPDBResidueInfo()
        info.SetChainId(chain)
        info.SetResidueName(resname)
        info.SetResidueNumber(resnum)
        info.SetIsHeteroAtom(False)
        info.SetName(f" {name:<3}")
        atom = rw.GetAtomWithIdx(idx)
        atom.SetPDBResidueInfo(info)
        atom.SetDoubleProp("_KollmanCharge", charge)
        atom.SetProp("_AD4Type", ad4)
        coords.append((float(i), 0.0, 0.0))

    mol = rw.GetMol()
    conf = Chem.Conformer(mol.GetNumAtoms())
    for i, c in enumerate(coords):
        conf.SetAtomPosition(i, c)
    mol.AddConformer(conf, assignId=True)
    return mol


def test_write_format_kolom_dan_charge(tmp_path):
    mol = _mol_2_chains()
    out_path = tmp_path / "rec.pdbqt"
    ReceptorPDBQTWriter().write(mol, out_path)

    lines = out_path.read_text().splitlines()
    atom_lines = [l for l in lines if l.startswith("ATOM")]
    assert len(atom_lines) == 3

    first = atom_lines[0]
    assert first[:6].strip() == "ATOM"
    assert "-0.416" in first or "-0.4157" in first  # kolom charge Kollman N
    assert first.rstrip().endswith("NA")  # kolom tipe AD4


def test_write_ter_di_antara_chain_berbeda(tmp_path):
    mol = _mol_2_chains()  # 2 atom chain A, 1 atom chain B
    out_path = tmp_path / "rec.pdbqt"
    ReceptorPDBQTWriter().write(mol, out_path)
    text = out_path.read_text()
    assert text.count("TER") == 2  # 1 di transisi A->B, 1 di akhir file


def test_write_tanpa_conformer_raise(tmp_path):
    mol = Chem.MolFromSmiles("CCO")
    with pytest.raises(ValueError):
        ReceptorPDBQTWriter().write(mol, tmp_path / "x.pdbqt")
