"""Test RedockingValidator dgn koordinat sintetis (nilai RMSD diketahui/terkontrol)."""

import numpy as np
import pytest

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem

from chemflow.docking.rmsd_validation import RedockingValidator


def _native_pdb_block(coords):
    """Bangun blok PDB 3-atom C-C-O sederhana dari daftar koordinat (x,y,z)."""
    names = ["C1", "C2", "O1"]
    elems = ["C", "C", "O"]
    lines = []
    for i, ((x, y, z), name, el) in enumerate(zip(coords, names, elems), start=1):
        lines.append(
            f"HETATM{i:>5} {name:<4} LIG A   1    "
            f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00          {el:>2}\n"
        )
    return "".join(lines) + "END\n"


def _make_pose_mol(coords):
    mol = Chem.RWMol()
    for elem in ("C", "C", "O"):
        mol.AddAtom(Chem.Atom(elem))
    mol.AddBond(0, 1, Chem.BondType.SINGLE)
    mol.AddBond(1, 2, Chem.BondType.SINGLE)
    m = mol.GetMol()
    conf = Chem.Conformer(3)
    for i, c in enumerate(coords):
        conf.SetAtomPosition(i, c)
    m.AddConformer(conf, assignId=True)
    Chem.SanitizeMol(m, catchErrors=True)
    return m


_BASE_COORDS = [(0.0, 0.0, 0.0), (1.5, 0.0, 0.0), (2.2, 1.3, 0.0)]


def test_rmsd_identik_mendekati_nol():
    validator = RedockingValidator()
    native_block = _native_pdb_block(_BASE_COORDS)
    pose = _make_pose_mol(_BASE_COORDS)

    result = validator.validate(native_block, pose, "TEST_LIG")
    assert result.rmsd is not None
    assert result.rmsd < 0.1
    assert result.status == "good"


def test_rmsd_translasi_rigid_tetap_mendekati_nol():
    """RMSD dgn optimal superposition harus tetap kecil meski pose ditranslasi
    rigid (bukan didistorsi): translasi murni harus terkompensasi alignment."""
    validator = RedockingValidator()
    native_block = _native_pdb_block(_BASE_COORDS)
    translated = [(x + 10.0, y - 5.0, z + 3.0) for x, y, z in _BASE_COORDS]
    pose = _make_pose_mol(translated)

    result = validator.validate(native_block, pose, "TEST_LIG")
    assert result.rmsd is not None
    assert result.rmsd < 0.1


def test_rmsd_distorsi_signifikan_terdeteksi_buruk():
    """Satu atom digeser jauh (bukan transformasi rigid) -> RMSD besar, status 'poor'."""
    validator = RedockingValidator(threshold_good=2.0, threshold_acceptable=3.0)
    native_block = _native_pdb_block(_BASE_COORDS)
    distorted = list(_BASE_COORDS)
    distorted[2] = (distorted[2][0] + 15.0, distorted[2][1], distorted[2][2])  # geser atom O jauh
    pose = _make_pose_mol(distorted)

    result = validator.validate(native_block, pose, "TEST_LIG")
    assert result.rmsd is not None
    assert result.rmsd > 3.0
    assert result.status == "poor"


def test_klasifikasi_status():
    validator = RedockingValidator(threshold_good=2.0, threshold_acceptable=3.0)
    assert validator._classify(1.0) == "good"
    assert validator._classify(2.5) == "acceptable"
    assert validator._classify(4.0) == "poor"


def test_kabsch_align_translasi_murni():
    mobile = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    target = mobile + np.array([5.0, -2.0, 1.0])
    aligned = RedockingValidator._kabsch_align(mobile, target)
    assert np.allclose(aligned, target, atol=1e-8)


def test_validate_gagal_parse_native_tidak_raise():
    validator = RedockingValidator()
    pose = _make_pose_mol(_BASE_COORDS)
    result = validator.validate("BUKAN BLOK PDB VALID SAMA SEKALI", pose, "TEST")
    assert result.status == "gagal"
    assert result.rmsd is None
