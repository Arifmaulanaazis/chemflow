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
    assert result.method == "CalcRMS"


def test_rmsd_pose_bergeser_terdeteksi_karena_dihitung_pada_posisi_asli():
    """Pose yang bentuknya sama tetapi bergeser dari posisi kristal tidak boleh terbaca baik:
    RMSD tidak disuperposisi, jadi translasi rigid ikut terhitung."""
    validator = RedockingValidator()
    native_block = _native_pdb_block(_BASE_COORDS)
    shift = (10.0, -5.0, 3.0)
    pose = _make_pose_mol([(x + shift[0], y + shift[1], z + shift[2]) for x, y, z in _BASE_COORDS])

    result = validator.validate(native_block, pose, "TEST_LIG")
    assert result.method == "CalcRMS"
    assert result.rmsd == pytest.approx(np.linalg.norm(shift), abs=1e-2)
    assert result.status == "poor"


def test_rmsd_memperhitungkan_simetri_atom_setara():
    """Urutan atom ujung yang setara secara simetri tidak boleh mempengaruhi RMSD."""
    native_coords = [(0.0, 0.0, 0.0), (1.5, 0.5, 0.0), (3.0, 0.0, 0.0)]
    lines = "".join(
        f"HETATM{i:>5} C{i}   LIG A   1    {x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00           C\n"
        for i, (x, y, z) in enumerate(native_coords, start=1)
    ) + "END\n"

    mol = Chem.RWMol()
    for _ in range(3):
        mol.AddAtom(Chem.Atom("C"))
    mol.AddBond(0, 1, Chem.BondType.SINGLE)
    mol.AddBond(1, 2, Chem.BondType.SINGLE)
    pose = mol.GetMol()
    conf = Chem.Conformer(3)
    for i, c in enumerate(reversed(native_coords)):       # atom ujung ditukar urutannya
        conf.SetAtomPosition(i, c)
    pose.AddConformer(conf, assignId=True)
    Chem.SanitizeMol(pose, catchErrors=True)

    result = RedockingValidator().validate(lines, pose, "SIM")
    assert result.method == "CalcRMS"
    assert result.rmsd < 0.01


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


def test_fallback_greedy_juga_tanpa_superposisi(monkeypatch):
    validator = RedockingValidator()
    monkeypatch.setattr(validator, "_try_calc_rms", lambda probe, ref: None)
    native_block = _native_pdb_block(_BASE_COORDS)

    identik = validator.validate(native_block, _make_pose_mol(_BASE_COORDS), "TEST_LIG")
    assert identik.method == "fallback_greedy" and identik.rmsd < 0.1

    shift = (10.0, -5.0, 3.0)
    bergeser = validator.validate(
        native_block, _make_pose_mol([(x + shift[0], y + shift[1], z + shift[2]) for x, y, z in _BASE_COORDS]),
        "TEST_LIG")
    assert bergeser.method == "fallback_greedy"
    assert bergeser.rmsd > 10.0          # pemetaan greedy hanya perkiraan, tetapi pergeseran 11,6 A tetap terlihat
    assert bergeser.status == "poor"


def test_kedua_metode_gagal_menghasilkan_status_gagal(monkeypatch):
    validator = RedockingValidator()
    monkeypatch.setattr(validator, "_try_calc_rms", lambda probe, ref: None)
    monkeypatch.setattr(validator, "_fallback_greedy_rmsd", lambda probe, ref: None)
    result = validator.validate(_native_pdb_block(_BASE_COORDS), _make_pose_mol(_BASE_COORDS), "TEST_LIG")
    assert result.status == "gagal" and result.rmsd is None and "greedy" in result.note


def test_catatan_menyebut_tanpa_superposisi():
    result = RedockingValidator().validate(_native_pdb_block(_BASE_COORDS), _make_pose_mol(_BASE_COORDS), "TEST")
    assert "tanpa superposisi" in result.note


def test_validate_gagal_parse_native_tidak_raise():
    validator = RedockingValidator()
    pose = _make_pose_mol(_BASE_COORDS)
    result = validator.validate("BUKAN BLOK PDB VALID SAMA SEKALI", pose, "TEST")
    assert result.status == "gagal"
    assert result.rmsd is None
