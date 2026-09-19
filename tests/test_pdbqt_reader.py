"""Test read_pdbqt: parsing multi-MODEL PDBQT hasil Vina -> daftar RDKit Mol."""

import pytest

rdkit = pytest.importorskip("rdkit")

from chemflow.io.pdbqt_reader import read_pdbqt, _guess_element

_MULTI_POSE_PDBQT = """\
MODEL 1
REMARK VINA RESULT:    -6.059      0.000      0.000
ATOM      1  C1  LIG A   1      -1.853  14.311  16.658  1.00  0.00     0.100 A
ATOM      2  N1  LIG A   1      -2.797  14.235  14.491  1.00  0.00    -0.200 N
ATOM      3  HN1 LIG A   1      -3.500  14.200  13.800  1.00  0.00     0.150 HD
ENDMDL
MODEL 2
REMARK VINA RESULT:    -5.664      1.200      2.300
ATOM      1  C1  LIG A   1      -1.900  14.400  16.700  1.00  0.00     0.100 A
ATOM      2  N1  LIG A   1      -2.850  14.300  14.550  1.00  0.00    -0.200 N
ATOM      3  HN1 LIG A   1      -3.550  14.250  13.850  1.00  0.00     0.150 HD
ENDMDL
"""


def test_read_pdbqt_multi_model(tmp_path):
    path = tmp_path / "out.pdbqt"
    path.write_text(_MULTI_POSE_PDBQT)

    mols = read_pdbqt(path)
    assert len(mols) == 2
    assert mols[0].GetNumAtoms() == 3  # mode 1 = pose terbaik, urutan pertama


def test_read_pdbqt_file_tidak_ada_tidak_raise(tmp_path):
    mols = read_pdbqt(tmp_path / "tidak_ada.pdbqt")
    assert mols == []


def test_read_pdbqt_file_kosong_tidak_raise(tmp_path):
    path = tmp_path / "kosong.pdbqt"
    path.write_text("")
    mols = read_pdbqt(path)
    assert mols == []


def test_guess_element_dari_tipe_ad4():
    assert _guess_element("HN1", "HD") == "H"
    assert _guess_element("C1", "A") == "C"
    assert _guess_element("N1", "NA") == "N"
    assert _guess_element("O1", "OA") == "O"


def test_guess_element_fallback_nama_atom():
    assert _guess_element("Cl1", "") == "Cl"
    assert _guess_element("X", "") == "X"
