"""Test resume: checkpoint docking per run, checkpoint ligan/reseptor, SMILES PubChem, Ctrl+C, dan merge."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from rdkit import Chem

import chemflow.pipeline as pipeline_module
from chemflow.chem.ligand_preparer import LigandPrepResult
from chemflow.checkpoints import load_ligand_prep, load_receptor, save_ligand_prep, save_receptor
from chemflow.config import PipelineConfig
from chemflow.docking.docking_matrix import DockingOrchestrator, DockingRunResult, ReceptorDockingTarget
from chemflow.docking.grid_box import GridBox
from chemflow.io.pdb_fetcher import NativeLigand
from chemflow.pipeline import Pipeline
from chemflow.state import RunState


class _Runner:
    """VinaRunner palsu: tulis keluaran PDBQT, catat pemanggilan, gagal untuk nama tertentu."""

    def __init__(self, fail=(), interrupt_on=None):
        self.calls, self.fail, self.interrupt_on = [], set(fail), interrupt_on

    def run(self, receptor_pdbqt, ligand_pdbqt, output_pdbqt, log_file, grid_box, **kwargs):
        name = ligand_pdbqt.stem
        self.calls.append((name, output_pdbqt.parent.parent.name))
        if name == self.interrupt_on:
            raise KeyboardInterrupt
        if name in self.fail:
            raise RuntimeError(f"Vina gagal (simulasi) untuk {name}")
        output_pdbqt.write_text("MODEL 1\nENDMDL\n")
        return [{"mode": 1, "affinity": -7.0 - len(name) / 10, "rmsd_lb": 0.0, "rmsd_ub": 0.0}]


def _target(key="R1"):
    return ReceptorDockingTarget(key=key, pdb_code=key, receptor_pdbqt=Path(f"{key}.pdbqt"),
                                 receptor_clean_pdb=Path(f"{key}_clean.pdb"),
                                 grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))


LIGANDS = {"LigA": Path("LigA.pdbqt"), "LigB": Path("LigB.pdbqt"), "LigCC": Path("LigCC.pdbqt")}


def _run(tmp_path, runner, resume, **kwargs):
    return DockingOrchestrator(runner).run_matrix(
        LIGANDS, [_target()], tmp_path, n_replicates=2, show_progress=False, resume=resume, **kwargs)


def test_setiap_run_menulis_checkpoint_json(tmp_path):
    _run(tmp_path, _Runner(), resume=False)
    files = sorted(p.name for p in (tmp_path / "R1" / "LigA").glob("*.json"))
    assert files == ["rep01.json", "rep02.json"]


def test_resume_tidak_mengulang_run_sukses(tmp_path):
    first = _run(tmp_path, _Runner(), resume=False, base_seed=None)
    runner = _Runner()
    second = _run(tmp_path, runner, resume=True)

    assert runner.calls == []
    assert len(second) == len(first) == 6
    assert all(r.reused and r.success for r in second)
    assert [r.seed for r in second] == [r.seed for r in first]
    assert [r.best_affinity for r in second] == [r.best_affinity for r in first]
    assert all(r.output_pdbqt.exists() for r in second)


def test_resume_tanpa_flag_menjalankan_semuanya_lagi(tmp_path):
    _run(tmp_path, _Runner(), resume=False)
    runner = _Runner()
    results = _run(tmp_path, runner, resume=False)
    assert len(runner.calls) == 6 and not any(r.reused for r in results)


def test_resume_mengulang_run_yang_gagal_saja(tmp_path):
    first = _run(tmp_path, _Runner(fail={"LigB"}), resume=False)
    assert sum(not r.success for r in first) == 2

    runner = _Runner()
    second = _run(tmp_path, runner, resume=True)
    assert sorted(name for name, _ in runner.calls) == ["LigB", "LigB"]
    assert all(r.success for r in second)
    assert {r.ligand_name for r in second if r.reused} == {"LigA", "LigCC"}


def test_resume_mengulang_run_bila_pdbqt_keluaran_hilang(tmp_path):
    first = _run(tmp_path, _Runner(), resume=False)
    victim = next(r for r in first if r.ligand_name == "LigA" and r.replicate == 2)
    victim.output_pdbqt.unlink()

    runner = _Runner()
    _run(tmp_path, runner, resume=True)
    assert runner.calls == [("LigA", "R1")]


def test_resume_mengabaikan_checkpoint_rusak(tmp_path):
    _run(tmp_path, _Runner(), resume=False)
    (tmp_path / "R1" / "LigA" / "rep01.json").write_text('{"terpotong": ', encoding="utf-8")
    runner = _Runner()
    _run(tmp_path, runner, resume=True)
    assert runner.calls == [("LigA", "R1")]


def test_ctrl_c_menyisakan_checkpoint_yang_sudah_selesai_dan_resume_menyelesaikan_sisanya(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, _Runner(interrupt_on="LigB"), resume=False)

    runner = _Runner()
    results = _run(tmp_path, runner, resume=True)
    assert len(results) == 6 and all(r.success for r in results)
    assert sorted(name for name, _ in runner.calls) == ["LigB", "LigB", "LigCC", "LigCC"]
    assert {r.ligand_name for r in results if r.reused} == {"LigA"}


def test_docking_run_result_round_trip_path_relatif(tmp_path):
    result = DockingRunResult(ligand_name="L", receptor_key="R", replicate=2, seed=5,
                              poses=[{"mode": 1, "affinity": -6.5}], output_pdbqt=tmp_path / "R" / "L" / "o.pdbqt",
                              log_path=tmp_path / "R" / "L" / "o.log")
    data = result.to_dict(tmp_path)
    assert data["output_pdbqt"] == "R/L/o.pdbqt"
    moved = tmp_path.parent / "pindah"
    again = DockingRunResult.from_dict(data, moved)
    assert again.output_pdbqt == moved / "R" / "L" / "o.pdbqt" and again.reused and again.best_affinity == -6.5


def _prep(tmp_path, name="Etanol", smiles="CCO"):
    directory = tmp_path / "ligands" / name
    directory.mkdir(parents=True)
    pdb, pdbqt = directory / f"{name}.pdb", directory / f"{name}.pdbqt"
    pdb.write_text("ATOM\n")
    pdbqt.write_text("ROOT\n")
    return directory, LigandPrepResult(name=name, smiles=smiles, mol=None, image_path=None, pdb_path=pdb,
                                       pdbqt_path=pdbqt, force_field_used="MMFF94", minimized_energy=-3.2)


def test_checkpoint_ligan_round_trip_dengan_lipinski(tmp_path):
    directory, result = _prep(tmp_path)
    save_ligand_prep(directory, result, {"ligand": "Etanol", "MW": 46.07}, tmp_path)
    loaded, lipinski = load_ligand_prep(directory, tmp_path, expected_smiles="CCO")
    assert loaded.pdbqt_path == result.pdbqt_path and loaded.force_field_used == "MMFF94"
    assert loaded.mol is None and lipinski == {"ligand": "Etanol", "MW": 46.07}


def test_checkpoint_ligan_ditolak_bila_smiles_berubah_atau_berkas_hilang(tmp_path):
    directory, result = _prep(tmp_path)
    save_ligand_prep(directory, result, None, tmp_path)
    assert load_ligand_prep(directory, tmp_path, expected_smiles="CO") is None
    assert load_ligand_prep(directory, tmp_path) is not None
    result.pdbqt_path.unlink()
    assert load_ligand_prep(directory, tmp_path) is None
    assert load_ligand_prep(tmp_path / "tidak_ada", tmp_path) is None


def test_checkpoint_reseptor_round_trip_termasuk_native_dan_gridbox(tmp_path):
    directory = tmp_path / "receptors" / "R1"
    directory.mkdir(parents=True)
    pdbqt, clean = directory / "R1_docking.pdbqt", directory / "R1_clean.pdb"
    pdbqt.write_text("x")
    clean.write_text("y")
    target = ReceptorDockingTarget(key="R1", pdb_code="6LU7", receptor_pdbqt=pdbqt, receptor_clean_pdb=clean,
                                   grid_box=GridBox.from_manual(1, 2, 3, 24, 24, 24, ref_label="N3_A1"))
    line = "HETATM    1  C1  N3  A   1       1.000   2.000   3.000  1.00  0.00           C\n"
    native = NativeLigand(chain="A", resname="N3", resnum=1, atom_lines=[line], center_x=1.0, center_y=2.0,
                          center_z=3.0)
    save_receptor(directory, target, native, tmp_path)

    loaded_target, loaded_native = load_receptor(directory, tmp_path)
    assert loaded_target.grid_box == target.grid_box and loaded_target.pdb_code == "6LU7"
    assert loaded_native.label == "N3_A1" and loaded_native.atom_lines == [line]
    assert loaded_native.to_pdb_block() == native.to_pdb_block()

    save_receptor(directory, target, None, tmp_path)
    assert load_receptor(directory, tmp_path)[1] is None
    pdbqt.unlink()
    assert load_receptor(directory, tmp_path) is None


@pytest.fixture
def make_pipeline(tmp_path):
    ligand = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Etanol", "Metanol"], "smiles": ["CCO", "CO"]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)

    def build(resume=False, **overrides):
        cfg = PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=tmp_path / "out",
                             openbabel_path=ligand, show_progress=False, **overrides)
        return Pipeline(cfg, resume=resume)

    build.ligand, build.receptor = ligand, receptor
    return build


class _Preparer:
    """LigandPreparer palsu yang menulis berkas dan mengembalikan mol RDKit sungguhan (untuk Lipinski)."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def prepare(self, name, smiles, output_dir, **kwargs):
        self.calls.append(name)
        if name in self.fail:
            raise ValueError("SMILES tidak valid (simulasi)")
        output_dir.mkdir(parents=True, exist_ok=True)
        pdb, pdbqt = output_dir / f"{name}.pdb", output_dir / f"{name}.pdbqt"
        pdb.write_text("ATOM\n")
        pdbqt.write_text("ROOT\n")
        return LigandPrepResult(name=name, smiles=smiles, mol=Chem.MolFromSmiles(smiles), image_path=None,
                                pdb_path=pdb, pdbqt_path=pdbqt, force_field_used="MMFF94", minimized_energy=None)


def _records(pipeline):
    from chemflow.io.excel_ligands import read_ligands
    return read_ligands(pipeline.cfg.ligand_excel)


def test_prepare_ligands_resume_memakai_checkpoint_tanpa_memanggil_preparer(make_pipeline):
    first = make_pipeline()
    first._ligand_preparer = _Preparer()
    records = _records(first)
    results = first._prepare_ligands(records)
    lipinski = first._compute_lipinski(results)
    assert len(results) == 2 and {r["ligand"] for r in lipinski} == {"Etanol", "Metanol"}

    second = make_pipeline(resume=True)
    second._ligand_preparer = _Preparer(fail={"Etanol", "Metanol"})   # kalau dipanggil, ligan gagal
    again = second._prepare_ligands(records)
    assert set(again) == {"Etanol", "Metanol"} and second._ligand_preparer.calls == []
    assert again["Etanol"].mol is None
    assert second._compute_lipinski(again) == lipinski
    assert second._reused["ligan siap"] == 2


def test_prepare_ligands_resume_hanya_menyiapkan_yang_belum_selesai(make_pipeline):
    first = make_pipeline()
    first._ligand_preparer = _Preparer(fail={"Metanol"})
    records = _records(first)
    assert set(first._prepare_ligands(records)) == {"Etanol"}
    assert first.failed_ligands == ["Metanol"]

    second = make_pipeline(resume=True)
    second._ligand_preparer = _Preparer()
    assert set(second._prepare_ligands(records)) == {"Etanol", "Metanol"}
    assert second._ligand_preparer.calls == ["Metanol"]


def test_ligan_run_baru_tidak_memakai_checkpoint_lama(make_pipeline):
    first = make_pipeline()
    first._ligand_preparer = _Preparer()
    records = _records(first)
    first._prepare_ligands(records)

    again = make_pipeline()                       # bukan resume
    again._ligand_preparer = _Preparer()
    again._prepare_ligands(records)
    assert sorted(again._ligand_preparer.calls) == ["Etanol", "Metanol"]


class _Resolver:
    lookups = []

    def __init__(self, *args, **kwargs):
        pass

    def resolve(self, name):
        _Resolver.lookups.append(name)
        return {"Etanol": "CCO"}.get(name)


def test_smiles_pubchem_dan_kegagalannya_dicheckpoint(tmp_path, monkeypatch):
    ligand = tmp_path / "wide.xlsx"
    pd.DataFrame({"G1": ["Etanol", "Tidakada"], "G2": ["Etanol", None]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)
    cfg = PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=tmp_path / "out",
                         openbabel_path=ligand, show_progress=False, interactive_pubchem_fallback=False)
    monkeypatch.setattr(pipeline_module, "PubChemResolver", _Resolver)

    _Resolver.lookups = []
    first = Pipeline(cfg)
    records = first._read_and_resolve_ligands()
    assert [r.smiles for r in records] == ["CCO", "CCO"]              # senyawa kembar hanya dicari sekali
    assert _Resolver.lookups == ["Etanol", "Tidakada"]
    assert first.failed_ligands == ["Tidakada"]

    _Resolver.lookups = []
    second = Pipeline(cfg, resume=True)
    again = second._read_and_resolve_ligands()
    assert _Resolver.lookups == []                                    # tanpa PubChem dan tanpa prompt ulang
    assert [r.smiles for r in again] == ["CCO", "CCO"]
    assert second.failed_ligands == ["Tidakada"]
    assert [r.safe_name for r in again] == [r.safe_name for r in records]


def test_panjang_nama_file_ligan_dipertahankan_saat_resume(make_pipeline, monkeypatch):
    import json

    first = make_pipeline()
    first._read_and_resolve_ligands()
    saved = RunState(first.cfg.output_dir).ligands_path
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert payload["name_length"] >= 8

    # Folder dipindah ke path yang lebih panjang: panjang nama harus tetap yang tersimpan, bukan dihitung ulang,
    # supaya nama file ligan (dan checkpoint-nya) tidak berubah.
    payload["name_length"] = 9
    saved.write_text(json.dumps(payload), encoding="utf-8")
    second = make_pipeline(resume=True)
    records = second._read_and_resolve_ligands()
    assert all(len(r.safe_name) <= 9 for r in records)


def test_run_ctrl_c_mengembalikan_130_dan_menunjukkan_perintah_resume(make_pipeline, caplog):
    pipeline = make_pipeline()

    def batal():
        raise KeyboardInterrupt

    pipeline._read_and_resolve_ligands = batal
    with caplog.at_level("INFO", logger="chemflow"):
        pipeline.log.propagate = True
        assert pipeline.run() == 130
    assert "chemflow resume --output" in caplog.text
    state = RunState(pipeline.cfg.output_dir)
    assert state.exists() and state.is_unfinished()


def test_run_baru_di_folder_yang_belum_selesai_memberi_peringatan_dan_membersihkan_checkpoint(make_pipeline, caplog):
    first = make_pipeline()
    first._begin()
    stale = first.cfg.docking_dir / "R1" / "L" / "rep01.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")

    second = make_pipeline()
    second.log.propagate = True
    with caplog.at_level("WARNING", logger="chemflow"):
        second._begin()
    assert "chemflow resume --output" in caplog.text
    assert not stale.exists()


def test_resume_begin_memuat_cache_admet_dan_menyimpan_override(make_pipeline):
    first = make_pipeline()
    first._begin()
    from chemflow.state import write_json_atomic
    write_json_atomic(first._state.admet_cache_path, {"CCO": {"hERG": 0.1}})

    resumed_cfg = first._state.load_config()
    resumed_cfg.log_level = "DEBUG"
    resumed = Pipeline(resumed_cfg, resume=True)
    resumed._begin()
    assert resumed._admet_cache == {"CCO": {"hERG": 0.1}}
    assert RunState(resumed.cfg.output_dir).load_config().log_level == "DEBUG"


def _clean_receptor(path):
    mol = Chem.RWMol()
    idx = mol.AddAtom(Chem.Atom("C"))
    info = Chem.AtomPDBResidueInfo()
    info.SetChainId("A")
    info.SetResidueName("ALA")
    info.SetResidueNumber(1)
    info.SetName(" CA ")
    mol.GetAtomWithIdx(idx).SetPDBResidueInfo(info)
    built = mol.GetMol()
    conf = Chem.Conformer(1)
    conf.SetAtomPosition(0, (0.0, 0.0, 0.0))
    built.AddConformer(conf, assignId=True)
    Chem.MolToPDBFile(built, str(path))


def _ligand_mol():
    from rdkit.Chem import AllChem
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    return mol


def test_merge_poses_resume_melewati_kompleks_lengkap_dari_run_yang_dipakai_ulang(make_pipeline, tmp_path, monkeypatch):
    pipeline = make_pipeline(resume=True)
    clean = tmp_path / "clean.pdb"
    _clean_receptor(clean)
    target = ReceptorDockingTarget(key="T", pdb_code="T", receptor_pdbqt=tmp_path / "d.pdbqt",
                                   receptor_clean_pdb=clean, grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))
    out = pipeline.cfg.complex_dir / "T" / "LigA_complex.pdb"
    out.parent.mkdir(parents=True)
    out.write_text("ATOM\n")
    out.with_suffix(".json").write_text("{}")

    calls = []
    monkeypatch.setattr(pipeline_module, "read_pdbqt", lambda path, logger=None: calls.append(path) or [_ligand_mol()])

    reused = DockingRunResult(ligand_name="LigA", receptor_key="T", replicate=1, seed=1,
                              poses=[{"affinity": -5.0}], output_pdbqt=tmp_path / "r.pdbqt", reused=True)
    pipeline._merge_poses([reused], [target])
    assert calls == [] and pipeline._reused["kompleks"] == 1

    fresh = DockingRunResult(ligand_name="LigA", receptor_key="T", replicate=1, seed=1,
                             poses=[{"affinity": -5.0}], output_pdbqt=tmp_path / "r.pdbqt")
    pipeline._merge_poses([fresh], [target])
    assert calls == [tmp_path / "r.pdbqt"]


def test_merge_poses_tanpa_json_sidecar_dianggap_belum_selesai(make_pipeline, tmp_path, monkeypatch):
    pipeline = make_pipeline(resume=True)
    clean = tmp_path / "clean.pdb"
    _clean_receptor(clean)
    target = ReceptorDockingTarget(key="T", pdb_code="T", receptor_pdbqt=tmp_path / "d.pdbqt",
                                   receptor_clean_pdb=clean, grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))
    out = pipeline.cfg.complex_dir / "T" / "LigA_complex.pdb"
    out.parent.mkdir(parents=True)
    out.write_text("ATOM\n")                      # PDB separuh jadi: sidecar JSON (penanda selesai) belum ada

    monkeypatch.setattr(pipeline_module, "read_pdbqt", lambda path, logger=None: [_ligand_mol()])
    reused = DockingRunResult(ligand_name="LigA", receptor_key="T", replicate=1, seed=1,
                              poses=[{"affinity": -5.0}], output_pdbqt=tmp_path / "r.pdbqt", reused=True)
    pipeline._merge_poses([reused], [target])
    assert out.with_suffix(".json").exists()


def test_stream_process_membunuh_proses_anak_saat_diinterupsi(monkeypatch):
    from chemflow.utils import subprocess_stream

    class _Proc:
        stdout = SimpleNamespace(readline=lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
        killed = waited = 0

        def poll(self):
            return None

        def kill(self):
            _Proc.killed += 1

        def wait(self):
            _Proc.waited += 1
            return -9

    monkeypatch.setattr(subprocess_stream.subprocess, "Popen", lambda *a, **k: _Proc())
    with pytest.raises(KeyboardInterrupt):
        subprocess_stream.stream_process(["vina"])
    assert _Proc.killed == 1 and _Proc.waited == 1
