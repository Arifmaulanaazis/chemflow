"""Keamanan nama file: nama senyawa yang tidak lazim tidak boleh menghasilkan path yang gagal di Windows."""

import logging
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from chemflow.chem.ligand_preparer import LigandPreparer
from chemflow.config import PipelineConfig
from chemflow.docking.docking_matrix import DockingOrchestrator, DockingRunResult, ReceptorDockingTarget
from chemflow.docking.grid_box import GridBox
from chemflow.io.excel_ligands import read_ligands
from chemflow.io.excel_receptors import ReceptorEntry
from chemflow.io.pdb_fetcher import fetch_pdb
from chemflow.utils.name_sanitizer import sanitize_filename, unique_safe_names

_WEIRD_NAMES = [
    "CON", "nul.txt", "COM1", 'a<b>c|d?e*f:g"h', "α-Tocopherol", "β-Tocopherol", "阿司匹林", "咖啡因",
    "Aspirin", "ASPIRIN", "(+)-Catechin", "  spasi  ", "titik.", "-strip", "x" * 150,
]
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
_ILLEGAL = set('<>:"/\\|?*')


def _assert_windows_safe(name: str) -> None:
    assert name
    assert not (set(name) & _ILLEGAL)
    assert all(ord(ch) >= 32 for ch in name)
    assert not name.endswith((".", " "))
    assert name.split(".")[0].upper() not in _RESERVED
    assert len(name) <= 60


class _StubConverter:
    def mol_to_pdb(self, mol, path):
        from rdkit import Chem

        Chem.MolToPDBFile(mol, str(path))
        return path

    def pdb_to_pdbqt(self, pdb_path, output_pdbqt, is_receptor):
        output_pdbqt.write_text("REMARK stub pdbqt\n")
        return output_pdbqt


@pytest.fixture
def pipeline(tmp_path):
    from chemflow.pipeline import Pipeline

    ligand_path = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Etanol"], "smiles": ["CCO"]}).to_excel(ligand_path, index=False)
    receptor_path = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor_path, index=False)
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, output_dir=tmp_path / "out",
                          openbabel_path=ligand_path, merge_mode="best")
    return Pipeline(cfg)


def test_semua_nama_tidak_lazim_menjadi_aman_dan_unik():
    safe = unique_safe_names(_WEIRD_NAMES)
    assert len(safe) == len(_WEIRD_NAMES)
    assert len({s.lower() for s in safe}) == len(safe)
    for name in safe:
        _assert_windows_safe(name)


def test_read_ligands_mengisi_safe_name_unik_dan_memberi_peringatan(tmp_path, caplog):
    path = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": _WEIRD_NAMES, "smiles": ["C"] * len(_WEIRD_NAMES)}).to_excel(path, index=False)

    with caplog.at_level(logging.WARNING, logger="uji.nama"):
        records = read_ligands(path, logger=logging.getLogger("uji.nama"))

    assert [r.name for r in records] == [n.strip() for n in _WEIRD_NAMES]
    assert len({r.safe_name.lower() for r in records}) == len(records)
    for record in records:
        _assert_windows_safe(record.safe_name)
    assert any("ASPIRIN" in message and "ASPIRIN_2" in message for message in caplog.messages)


@pytest.mark.parametrize("name", _WEIRD_NAMES)
def test_ligand_preparer_menulis_2d_pdb_dan_pdbqt_dengan_nama_aman(tmp_path, name):
    preparer = LigandPreparer(_StubConverter())
    stem = sanitize_filename(name)

    result = preparer.prepare(name, "CCO", tmp_path / stem, generate_image=True)

    assert result.name == name
    assert result.image_path is not None and result.image_path.name == f"{stem}_2d.png"
    assert result.pdb_path.name == f"{stem}.pdb"
    assert result.pdbqt_path.name == f"{stem}.pdbqt"
    for path in (result.image_path, result.pdb_path, result.pdbqt_path):
        assert path.exists()
        _assert_windows_safe(path.name.split("_2d.png")[0].removesuffix(".pdb").removesuffix(".pdbqt"))


def test_docking_matrix_memakai_folder_aman_untuk_nama_ligan_aneh(tmp_path):
    class _Runner:
        def run(self, receptor_pdbqt, ligand_pdbqt, output_pdbqt, log_file, grid_box, **kwargs):
            return [{"mode": 1, "affinity": -6.0, "rmsd_lb": 0.0, "rmsd_ub": 0.0}]

    target = ReceptorDockingTarget(
        key="REC1", pdb_code="REC1", receptor_pdbqt=Path("r.pdbqt"), receptor_clean_pdb=Path("r.pdb"),
        grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20),
    )
    ligands = {name: Path("x.pdbqt") for name in ("CON", "a<b>c", "nul.txt")}

    results = DockingOrchestrator(_Runner()).run_matrix(ligands, [target], tmp_path, n_replicates=1,
                                                        show_progress=False)

    assert {r.ligand_name for r in results} == set(ligands)
    for name in ligands:
        assert (tmp_path / "REC1" / sanitize_filename(name)).is_dir()


def test_pipeline_prepare_ligands_memisahkan_nama_yang_hanya_beda_huruf_besar_kecil(pipeline, tmp_path):
    path = tmp_path / "dua.xlsx"
    pd.DataFrame({"name": ["Aspirin", "ASPIRIN"], "smiles": ["CCO", "CO"]}).to_excel(path, index=False)
    records = read_ligands(path)

    calls = []

    class _Preparer:
        def prepare(self, name, smiles, output_dir, **kwargs):
            calls.append((name, output_dir))
            return SimpleNamespace(smiles=smiles)

    pipeline._ligand_preparer = _Preparer()
    results = pipeline._prepare_ligands(records)

    assert set(results) == {"Aspirin", "ASPIRIN_2"}
    assert [output_dir.name for _, output_dir in calls] == ["Aspirin", "ASPIRIN_2"]

    rows = pipeline._ligand_summary_rows(records, results)
    assert [(r["name"], r["nama_file"], r["status"]) for r in rows] == [
        ("Aspirin", "Aspirin", "siap"), ("ASPIRIN", "ASPIRIN_2", "siap"),
    ]


def test_merge_poses_menulis_kompleks_dengan_nama_file_aman(pipeline, tmp_path, monkeypatch):
    import chemflow.pipeline as pipeline_module
    from rdkit import Chem
    from rdkit.Chem import AllChem

    receptor = Chem.RWMol()
    idx = receptor.AddAtom(Chem.Atom("C"))
    info = Chem.AtomPDBResidueInfo()
    info.SetChainId("A")
    info.SetResidueName("ALA")
    info.SetResidueNumber(1)
    info.SetName(" CA ")
    receptor.GetAtomWithIdx(idx).SetPDBResidueInfo(info)
    receptor_mol = receptor.GetMol()
    conformer = Chem.Conformer(1)
    conformer.SetAtomPosition(0, (0.0, 0.0, 0.0))
    receptor_mol.AddConformer(conformer, assignId=True)
    clean = tmp_path / "clean.pdb"
    Chem.MolToPDBFile(receptor_mol, str(clean))

    ligand = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(ligand, randomSeed=1)
    monkeypatch.setattr(pipeline_module, "read_pdbqt", lambda path, logger=None: [ligand])

    target = ReceptorDockingTarget(key="TEST", pdb_code="TEST", receptor_pdbqt=tmp_path / "d.pdbqt",
                                    receptor_clean_pdb=clean, grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))
    results = [DockingRunResult(ligand_name="a<b>:c", receptor_key="TEST", replicate=1, seed=1,
                                 poses=[{"affinity": -5.0}], output_pdbqt=tmp_path / "out.pdbqt")]

    pipeline._merge_poses(results, [target])

    assert (pipeline.cfg.complex_dir / "TEST" / f"{sanitize_filename('a<b>:c')}_complex.pdb").exists()


@pytest.mark.parametrize("output_length, expected", [(20, 60), (100, 60), (135, 53), (160, 41), (190, 16), (240, 8)])
def test_batas_panjang_nama_mengecil_saat_folder_output_dalam(output_length, expected):
    from chemflow.pipeline import _name_length_budget

    budget = _name_length_budget(output_length)
    assert budget == expected
    if budget > 8:
        assert output_length + 17 + 2 * budget <= 259
        assert output_length + 53 + budget <= 259


def test_read_ligands_menghormati_max_name_length(tmp_path):
    path = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["N" * 100, "N" * 101], "smiles": ["C", "CC"]}).to_excel(path, index=False)

    records = read_ligands(path, max_name_length=20)

    assert all(len(r.safe_name) <= 20 for r in records)
    assert records[0].safe_name != records[1].safe_name


def test_kunci_reseptor_tidak_memuat_karakter_terlarang():
    assert ReceptorEntry(pdb_code="6LU7", row_index=2).unique_key == "6LU7_R002"
    key = ReceptorEntry(pdb_code="6L/U:7", row_index=1).unique_key
    assert not (set(key) & _ILLEGAL)


@pytest.mark.parametrize("code", ["", "6LU", "6LU7X", "6L/7", "..\\x", "6LU 7", "CON"])
def test_fetch_pdb_menolak_kode_tidak_valid_sebelum_menyentuh_disk(tmp_path, code):
    destination = tmp_path / "cache"
    with pytest.raises(RuntimeError, match="tidak valid"):
        fetch_pdb(code, destination)
    assert not destination.exists()
