"""Test LipinskiCalculator: Ro5 & deskriptor tambahan, nilai dicek terhadap senyawa dikenal."""

import pytest

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem

from chemflow.chem.descriptors import LipinskiCalculator


def test_aspirin_lolos_ro5():
    mol = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
    result = LipinskiCalculator.calculate(mol)
    assert result.molecular_weight == pytest.approx(180.16, abs=0.1)
    assert result.violations <= 1
    assert result.passes_ro5 is True


def test_molekul_besar_melanggar_ro5():
    # Molekul besar berulang (>500 Da, banyak HBA/HBD) harus banyak pelanggaran.
    smiles = "OC(=O)" * 15 + "C"
    mol = Chem.MolFromSmiles(smiles)
    result = LipinskiCalculator.calculate(mol)
    assert result.molecular_weight > 500
    assert result.violations >= 2
    assert result.passes_ro5 is False


def test_violations_count_benar_untuk_air():
    mol = Chem.MolFromSmiles("O")
    result = LipinskiCalculator.calculate(mol)
    assert result.violations == 0
    assert result.hbd == 2  # H2O: 2 ikatan O-H, RDKit CalcNumLipinskiHBD menghitung per-H
    assert result.hba >= 0


def test_extended_descriptors_toluena():
    mol = Chem.MolFromSmiles("Cc1ccccc1")
    ext = LipinskiCalculator.calculate_extended(mol)
    assert ext.aromatic_rings == 1
    assert ext.rotatable_bonds == 0
    assert 0.0 <= ext.fraction_csp3 <= 1.0
    assert ext.tpsa == pytest.approx(0.0, abs=0.1)
