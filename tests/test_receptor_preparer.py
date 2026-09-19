"""
Test ReceptorPreparer dgn mol RDKit sintetis (dibangun manual, bonds &
koordinat eksplisit, tidak bergantung file PDB nyata/tool eksternal):
  - _clean(): residu air & ligan asli dibuang, residu HETATM "termodifikasi"
    (backbone N-CA-C lengkap, mis. MSE) DIPERTAHANKAN.
  - prepare_for_docking(): H polar-only + Kollman charge + tipe AD4 -> PDBQT
    tanpa tag torsi (ROOT/BRANCH/TORSDOF, reseptor harus rigid).
  - prepare_for_merge(): reseptor bersih, nol atom H, nol muatan.
"""

import pytest

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem

from chemflow.chem.receptor_preparer import ReceptorPreparer


def _add_residue_atom(rw, elem, resname, resnum, chain, atom_name, is_hetero, coord):
    idx = rw.AddAtom(Chem.Atom(elem))
    info = Chem.AtomPDBResidueInfo()
    info.SetChainId(chain)
    info.SetResidueName(resname)
    info.SetResidueNumber(resnum)
    info.SetIsHeteroAtom(is_hetero)
    info.SetName(f" {atom_name:<3}")
    rw.GetAtomWithIdx(idx).SetPDBResidueInfo(info)
    return idx, coord


def _build_synthetic_receptor():
    """1 residu standar (GLY, ATOM) + 1 residu 'termodifikasi' backbone-lengkap
    (MSE, HETATM tapi harus dipertahankan) + 1 air (HOH, harus dibuang) +
    1 ligan asli tanpa backbone (LIG, harus dibuang)."""
    rw = Chem.RWMol()
    coords = []

    # Residu 1: GLY, standar (ATOM)
    n1, c = _add_residue_atom(rw, "N", "GLY", 1, "A", "N", False, (0.0, 0.0, 0.0)); coords.append(c)
    ca1, c = _add_residue_atom(rw, "C", "GLY", 1, "A", "CA", False, (1.46, 0.0, 0.0)); coords.append(c)
    c1, c = _add_residue_atom(rw, "C", "GLY", 1, "A", "C", False, (2.0, 1.4, 0.0)); coords.append(c)
    o1, c = _add_residue_atom(rw, "O", "GLY", 1, "A", "O", False, (1.3, 2.4, 0.0)); coords.append(c)
    rw.AddBond(n1, ca1, Chem.BondType.SINGLE)
    rw.AddBond(ca1, c1, Chem.BondType.SINGLE)
    rw.AddBond(c1, o1, Chem.BondType.DOUBLE)

    # Residu 2: MSE, backbone lengkap tapi HETATM (harus dipertahankan)
    n2, c = _add_residue_atom(rw, "N", "MSE", 2, "A", "N", True, (3.3, 1.5, 0.0)); coords.append(c)
    ca2, c = _add_residue_atom(rw, "C", "MSE", 2, "A", "CA", True, (4.7, 1.5, 0.0)); coords.append(c)
    c2, c = _add_residue_atom(rw, "C", "MSE", 2, "A", "C", True, (5.3, 2.9, 0.0)); coords.append(c)
    o2, c = _add_residue_atom(rw, "O", "MSE", 2, "A", "O", True, (4.6, 3.9, 0.0)); coords.append(c)
    cb2, c = _add_residue_atom(rw, "C", "MSE", 2, "A", "CB", True, (5.5, 0.3, 0.0)); coords.append(c)
    se2, c = _add_residue_atom(rw, "Se", "MSE", 2, "A", "SE", True, (7.3, 0.3, 0.0)); coords.append(c)
    ce2, c = _add_residue_atom(rw, "C", "MSE", 2, "A", "CE", True, (8.1, 1.9, 0.0)); coords.append(c)
    rw.AddBond(n2, ca2, Chem.BondType.SINGLE)
    rw.AddBond(ca2, c2, Chem.BondType.SINGLE)
    rw.AddBond(c2, o2, Chem.BondType.DOUBLE)
    rw.AddBond(ca2, cb2, Chem.BondType.SINGLE)
    rw.AddBond(cb2, se2, Chem.BondType.SINGLE)
    rw.AddBond(se2, ce2, Chem.BondType.SINGLE)

    # Air (harus dibuang)
    ow, c = _add_residue_atom(rw, "O", "HOH", 10, "A", "O", True, (20.0, 0.0, 0.0)); coords.append(c)

    # Ligan asli tanpa backbone (harus dibuang)
    lg1, c = _add_residue_atom(rw, "C", "LIG", 20, "A", "C1", True, (30.0, 0.0, 0.0)); coords.append(c)
    lg2, c = _add_residue_atom(rw, "C", "LIG", 20, "A", "C2", True, (31.5, 0.0, 0.0)); coords.append(c)
    rw.AddBond(lg1, lg2, Chem.BondType.SINGLE)

    mol = rw.GetMol()
    conf = Chem.Conformer(mol.GetNumAtoms())
    for i, xyz in enumerate(coords):
        conf.SetAtomPosition(i, xyz)
    mol.AddConformer(conf, assignId=True)
    Chem.SanitizeMol(mol, catchErrors=True)
    return mol


def test_clean_mempertahankan_residu_termodifikasi_buang_air_dan_ligan():
    mol = _build_synthetic_receptor()
    preparer = ReceptorPreparer()
    cleaned = preparer._clean(mol, remove_waters=True, remove_hetero_ligands=True, keep_metals=True)

    resnames = set()
    for atom in cleaned.GetAtoms():
        info = atom.GetPDBResidueInfo()
        resnames.add(info.GetResidueName().strip())

    assert resnames == {"GLY", "MSE"}  # HOH & LIG terbuang, MSE dipertahankan
    assert cleaned.GetNumAtoms() == 11  # 4 (GLY) + 7 (MSE)


def test_prepare_for_merge_tanpa_h_tanpa_muatan(tmp_path):
    mol = _build_synthetic_receptor()
    preparer = ReceptorPreparer()
    out_pdb = tmp_path / "clean.pdb"
    preparer.prepare_for_merge(mol, out_pdb)

    result_mol = Chem.MolFromPDBFile(str(out_pdb), sanitize=False, removeHs=False)
    assert result_mol is not None
    assert all(a.GetAtomicNum() != 1 for a in result_mol.GetAtoms())  # nol H
    for atom in result_mol.GetAtoms():
        assert atom.GetFormalCharge() == 0

    text = out_pdb.read_text()
    assert "HOH" not in text
    assert "LIG" not in text
    assert "MSE" in text  # residu termodifikasi tetap ada di file merge


def _histidine_epsilon_pdb() -> str:
    """HIS netral tautomer epsilon (hanya HE2 pada NE2, ND1 tanpa H) dengan H
    eksplisit, koordinat diambil dari residu HIS A25 pada 1FKB."""
    atoms = [
        ("N", "N", -5.791, 1.917, 8.686), ("CA", "C", -5.944, 1.680, 10.114),
        ("C", "C", -4.667, 1.066, 10.631), ("O", "O", -4.039, 0.296, 9.902),
        ("CB", "C", -7.097, 0.749, 10.449), ("CG", "C", -8.341, 1.527, 10.841),
        ("ND1", "N", -8.305, 2.502, 11.741), ("CD2", "C", -9.594, 1.265, 10.371),
        ("CE1", "C", -9.570, 2.856, 11.861), ("NE2", "N", -10.318, 2.113, 11.060),
        ("H", "H", -5.652, 1.157, 8.076), ("HE2", "H", -11.295, 2.175, 11.006),
    ]
    lines = [
        f"ATOM  {serial:5d}  {name:<3s} HIS A  25    {x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {elem:>2s}"
        for serial, (name, elem, x, y, z) in enumerate(atoms, start=222)
    ]
    return "\n".join(lines + ["END", ""])


def test_prepare_for_merge_his_netral_ber_h_eksplisit_tidak_gagal_kekulize(tmp_path):
    """Regresi 1FKB: setelah semua H dibuang, cincin imidazol aromatik kehilangan
    NH-nya sehingga penulisan PDB melempar KekulizeException dan seluruh reseptor
    terbuang. File bersih tetap harus tertulis tanpa H."""
    pdb = tmp_path / "his.pdb"
    pdb.write_text(_histidine_epsilon_pdb())
    preparer = ReceptorPreparer()
    mol = preparer.load(pdb)

    out_pdb = tmp_path / "clean.pdb"
    result = preparer.prepare_for_merge(mol, out_pdb)

    assert result == out_pdb and out_pdb.stat().st_size > 0
    atom_lines = [l for l in out_pdb.read_text().splitlines() if l.startswith(("ATOM", "HETATM"))]
    assert len(atom_lines) == 10  # 10 atom berat, H dibuang
    assert all(l[76:78].strip() != "H" for l in atom_lines)
    assert any(l[12:16].strip() == "NE2" for l in atom_lines)


def test_prepare_for_docking_hasilkan_pdbqt_polar_h_dan_kollman(tmp_path):
    mol = _build_synthetic_receptor()
    preparer = ReceptorPreparer(kollman_fallback="zero")
    out_pdbqt = tmp_path / "docking.pdbqt"
    preparer.prepare_for_docking(mol, out_pdbqt)

    text = out_pdbqt.read_text()
    assert out_pdbqt.exists() and out_pdbqt.stat().st_size > 0

    # Reseptor harus rigid, tanpa tag pohon torsi.
    for banned in ("ROOT", "ENDROOT", "BRANCH", "TORSDOF"):
        assert banned not in text

    # Harus ada baris ATOM/HETATM dengan kolom charge (numerik) & tipe AD4.
    atom_lines = [l for l in text.splitlines() if l.startswith(("ATOM", "HETATM"))]
    assert len(atom_lines) > 11  # >= atom berat + H polar yang ditambahkan
    assert "TER" in text


def test_prepare_for_docking_gasteiger_fallback_tidak_error(tmp_path):
    mol = _build_synthetic_receptor()
    preparer = ReceptorPreparer(kollman_fallback="gasteiger")
    out_pdbqt = tmp_path / "docking2.pdbqt"
    result = preparer.prepare_for_docking(mol, out_pdbqt)
    assert result.exists()
