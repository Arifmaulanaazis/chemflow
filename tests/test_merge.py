"""Test ComplexMerger (docking/merge.py) dengan mol RDKit sintetis kecil."""

import json

import pytest

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem
from rdkit.Chem import AllChem

from chemflow.docking.merge import merge_complex


def _make_receptor_mol():
    mol = Chem.RWMol()
    coords = []
    for i, (elem, name) in enumerate([("N", "N"), ("C", "CA"), ("C", "C"), ("O", "O")]):
        idx = mol.AddAtom(Chem.Atom(elem))
        info = Chem.AtomPDBResidueInfo()
        info.SetChainId("A")
        info.SetResidueName("ALA")
        info.SetResidueNumber(1)
        info.SetIsHeteroAtom(False)
        info.SetName(f" {name:<3}")
        mol.GetAtomWithIdx(idx).SetPDBResidueInfo(info)
        coords.append((float(i), 0.0, 0.0))
    m = mol.GetMol()
    conf = Chem.Conformer(m.GetNumAtoms())
    for i, c in enumerate(coords):
        conf.SetAtomPosition(i, c)
    m.AddConformer(conf, assignId=True)
    Chem.SanitizeMol(m, catchErrors=True)
    return m


def _make_ligand_pose_mol():
    mol = Chem.MolFromSmiles("CCO")
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, randomSeed=42)
    return mol


def test_merge_menghasilkan_file_dengan_ter_dan_chain_terpisah(tmp_path):
    receptor = _make_receptor_mol()
    ligand = _make_ligand_pose_mol()
    out_path = tmp_path / "complex.pdb"

    result_path = merge_complex(receptor, ligand, out_path, ligand_name="Etanol")
    assert result_path.exists()

    text = result_path.read_text()
    assert text.count("TER") == 2  # setelah blok reseptor & setelah blok ligan
    assert "ETA" in text  # resname 3-huruf diturunkan dari "Etanol"
    # Chain ligan harus 'X' (chain pertama yang dicoba, tidak dipakai reseptor 'A')
    ligand_lines = [l for l in text.splitlines() if l.startswith("HETATM")]
    assert ligand_lines, "Harus ada baris HETATM untuk ligan"
    assert all(l[21] == "X" for l in ligand_lines)


def test_merge_raise_jika_mol_none(tmp_path):
    receptor = _make_receptor_mol()
    with pytest.raises(ValueError):
        merge_complex(receptor, None, tmp_path / "out.pdb")
    with pytest.raises(ValueError):
        merge_complex(None, _make_ligand_pose_mol(), tmp_path / "out.pdb")


def test_merge_atom_count_sesuai(tmp_path):
    receptor = _make_receptor_mol()
    ligand = _make_ligand_pose_mol()
    out_path = tmp_path / "complex.pdb"
    merge_complex(receptor, ligand, out_path, ligand_name="Test")

    text = out_path.read_text()
    atom_lines = [l for l in text.splitlines() if l.startswith(("ATOM", "HETATM"))]
    assert len(atom_lines) == receptor.GetNumAtoms() + ligand.GetNumAtoms()


def test_merge_menulis_sidecar_json_metadata(tmp_path):
    receptor = _make_receptor_mol()
    ligand = _make_ligand_pose_mol()
    out_path = tmp_path / "complex.pdb"
    merge_complex(receptor, ligand, out_path, ligand_name="Etanol", ligand_code="LIG1")

    sidecar = out_path.with_suffix(".json")
    assert sidecar.exists()
    metadata = json.loads(sidecar.read_text())
    assert metadata["ligand_name"] == "Etanol"
    assert metadata["ligand_code"] == "LIG1"
    assert metadata["ligand_chain"] == "X"
    assert metadata["ligand_resname"] == "ETA"
    assert metadata["is_native"] is False


def test_merge_sidecar_json_is_native_true(tmp_path):
    receptor = _make_receptor_mol()
    ligand = _make_ligand_pose_mol()
    out_path = tmp_path / "native_complex.pdb"
    merge_complex(receptor, ligand, out_path, ligand_name="Aspirin", is_native=True)

    metadata = json.loads(out_path.with_suffix(".json").read_text())
    assert metadata["is_native"] is True
