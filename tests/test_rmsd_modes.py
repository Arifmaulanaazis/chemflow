from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from rdkit import Chem

import chemflow.pipeline as pm
from chemflow.cli import build_parser
from chemflow.config import PipelineConfig
from chemflow.docking.docking_matrix import DockingRunResult
from chemflow.interaction.exporter import discover_jobs
from chemflow.state import RunState
from tests.test_native import make_pipeline, _context, _native_entry
from tests.test_pipeline_smoke import _fake_ligand_mol, _make_receptor_clean_pdb


def test_rmsd_only_parser_and_config(tmp_path):
    args = build_parser().parse_args(['run', '--rmsd-only', '--receptors', 'r.xlsx',
                                     '--rmsd-merge-mode', 'all', '--rmsd-interaction-mode', 'best'])
    assert args.ligands is None and args.rmsd_only
    receptor = tmp_path / 'r.xlsx'
    receptor.touch()
    cfg = PipelineConfig(ligand_excel=tmp_path / 'ignored.xlsx', receptor_excel=receptor, rmsd_only=True)
    assert cfg.ligand_excel is None and cfg.run_rmsd_validation and not cfg.run_admet
    assert not any((cfg.generate_charts, cfg.run_pca, cfg.run_hca, cfg.run_heatmap))
    state = RunState(tmp_path / 'out')
    state.save_config(cfg)
    resumed = state.load_config()
    assert resumed.rmsd_only and resumed.ligand_excel is None


@pytest.mark.parametrize('merge_mode,interaction_mode,counts', [('best', 'all', (1, 4)), ('all', 'best', (4, 1))])
def test_best_rmsd_in_other_pose_and_replicate(make_pipeline, tmp_path, monkeypatch, merge_mode, interaction_mode, counts):
    pipe = make_pipeline(run_rmsd_validation=True, merge_mode='best',
                         rmsd_merge_mode=merge_mode, rmsd_interaction_mode=interaction_mode)
    pipe._natives = [_native_entry()]
    mols = [_fake_ligand_mol() for _ in range(4)]
    for mol, rmsd in zip(mols, [4., 3., 2., .5]):
        mol.SetDoubleProp('test_rmsd', rmsd)
    monkeypatch.setattr(pm, 'read_pdbqt', lambda path, **kw: mols[:2] if path.stem == 'rep1' else mols[2:])
    class Validator:
        def __init__(self, *args, **kw): pass
        def validate(self, block, mol, label):
            return SimpleNamespace(rmsd=mol.GetDoubleProp('test_rmsd'), status='good', method='test', note='')
    monkeypatch.setattr(pm, 'RedockingValidator', Validator)
    results = [DockingRunResult('NATIVE_N3_A1', 'R1', i, i,
                               poses=[{'mode': 1, 'affinity': -10.}, {'mode': 2, 'affinity': -5.}],
                               output_pdbqt=tmp_path / f'rep{i}.pdbqt') for i in (1, 2)]
    rows = pipe._run_rmsd_validation(_context('R1'), results)
    assert (rows[0]['replicate'], rows[0]['mode'], rows[0]['rmsd_angstrom']) == (2, 2, .5)
    assert rows[0]['redock_affinity'] == -5.
    frame = pd.read_excel(pipe.cfg.output_dir / 'rmsd/hasil_rmsd.xlsx', sheet_name='Hasil Docking')
    assert len(frame) == 4 and frame.selected_best.sum() == 1
    clean = tmp_path / 'clean.pdb'
    _make_receptor_clean_pdb(clean)
    pipe._merge_rmsd_poses([SimpleNamespace(key='R1', receptor_clean_pdb=clean)])
    rmsd = pipe.cfg.output_dir / 'rmsd'
    assert len(list((rmsd / 'complexes').rglob('*.pdb'))) == counts[0]
    jobs, _ = discover_jobs(rmsd / 'interaction_source', rmsd / 'interaksi')
    assert len(jobs) == counts[1]
    if interaction_mode == 'best':
        assert 'rep02_mode02' in jobs[0].stem
    # Obsolete files left by an earlier all run must not enter the new export queue.
    (rmsd / 'interaction_source/complexes/R1/stale_complex.pdb').touch()
    assert len(discover_jobs(rmsd / 'interaction_source')[0]) == counts[1]
    assert not pipe.cfg.complex_dir.exists()
    # Rerun with best in the same output: remove only generated all-mode files.
    pipe.cfg.rmsd_merge_mode = pipe.cfg.rmsd_interaction_mode = 'best'
    pipe._merge_rmsd_poses([SimpleNamespace(key='R1', receptor_clean_pdb=clean)])
    assert len(list((rmsd / 'complexes').rglob('*.pdb'))) == 1
    assert len(discover_jobs(rmsd / 'interaction_source')[0]) == 1
    assert (rmsd / 'interaction_source/complexes/R1/stale_complex.pdb').exists()


def test_rmsd_only_skips_screening(make_pipeline, monkeypatch):
    pipe = make_pipeline(rmsd_only=True, run_similarity=False)
    for name in ('_read_and_resolve_ligands', '_prepare_ligands', '_run_admet', '_native_properties',
                 '_merge_poses', '_generate_charts', '_run_pca', '_run_hca'):
        monkeypatch.setattr(pipe, name, lambda *a, **k: pytest.fail('Screening stage was called'))
    class Orchestrator:
        def __init__(self, *a, **kw): pass
        def run_matrix(self, *a, **kw): pytest.fail('Screening matrix was called')
    monkeypatch.setattr(pm, 'DockingOrchestrator', Orchestrator)
    monkeypatch.setattr(pm, 'resolve_vina_executable', lambda *a, **k: Path('vina'))
    monkeypatch.setattr(pipe, '_prepare_receptors', lambda: ([], {'R1': {}}))
    monkeypatch.setattr(pipe, '_prepare_natives', lambda *a: [])
    monkeypatch.setattr(pipe, '_dock_natives', lambda *a: [])
    monkeypatch.setattr(pipe, '_run_rmsd_validation', lambda *a: [{'rmsd_angstrom': .5}])
    monkeypatch.setattr(pipe, '_merge_rmsd_poses', lambda *a: None)
    assert pipe.run() == 0
    assert pipe._state.read_progress()['finished']


def test_rmsd_only_no_native_fails(make_pipeline, monkeypatch):
    pipe = make_pipeline(rmsd_only=True, run_similarity=False)
    monkeypatch.setattr(pm, 'resolve_vina_executable', lambda *a, **k: Path('vina'))
    monkeypatch.setattr(pipe, '_prepare_receptors', lambda: ([], {}))
    assert pipe.run() == 1


def test_real_rmsd_selects_translated_pose_without_alignment(make_pipeline, tmp_path, monkeypatch):
    pipe = make_pipeline(run_rmsd_validation=True)
    pipe._natives = [_native_entry()]
    context = _context('R1')
    native = context['R1']['native']
    source = Chem.MolFromPDBBlock(native.to_pdb_block(), sanitize=False, removeHs=True)
    poses = []
    for distance in (3., .25):
        mol = Chem.Mol(source)
        conf = mol.GetConformer()
        for i in range(mol.GetNumAtoms()):
            xyz = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, (xyz.x, xyz.y + distance, xyz.z))
        poses.append(mol)
    monkeypatch.setattr(pm, 'read_pdbqt', lambda *a, **kw: poses)
    result = DockingRunResult('NATIVE_N3_A1', 'R1', 1, 10,
                              poses=[{'mode':1, 'affinity': -9.}, {'mode':2, 'affinity': -7.}],
                              output_pdbqt=tmp_path / 'rep1.pdbqt')
    best = pipe._run_rmsd_validation(context, [result])[0]
    assert best['mode'] == 2 and best['rmsd_angstrom'] == pytest.approx(.25)
    assert best['metode'] == 'CalcRMS'


def test_rmsd_interaction_export_failure_is_reported(make_pipeline, monkeypatch):
    from chemflow.interaction import BioviaUnavailableError
    pipe = make_pipeline(rmsd_only=True)
    def unavailable(*args, **kwargs):
        raise BioviaUnavailableError('BIOVIA unavailable')
    monkeypatch.setattr('chemflow.interaction.export_interactions', unavailable)
    pipe._run_rmsd_interactions()
    assert len(pipe.failed_interactions) == 1 and 'BIOVIA unavailable' in pipe.failed_interactions[0]


def test_interactions_rmsd_cli_routes_to_separate_complexes(tmp_path, monkeypatch):
    from chemflow.cli import main
    from chemflow.interaction.exporter import ExportSummary
    seen = {}
    def export(source, destination, **kwargs):
        seen.update(source=source, destination=destination)
        return ExportSummary()
    monkeypatch.setattr('chemflow.interaction.export_interactions', export)
    assert main(['interactions', '--output', str(tmp_path), '--rmsd', '--no-lock-input']) == 0
    assert seen == {'source': tmp_path / 'rmsd/interaction_source', 'destination': tmp_path / 'rmsd/interaksi'}


def test_rmsd_only_partial_missing_native_fails(make_pipeline, monkeypatch):
    pipe = make_pipeline(rmsd_only=True, run_similarity=False)
    monkeypatch.setattr(pm, 'resolve_vina_executable', lambda *a, **k: Path('vina'))
    monkeypatch.setattr(pipe, '_prepare_receptors', lambda: ([SimpleNamespace(key='R1'), SimpleNamespace(key='R2')], {'R1': {}}))
    monkeypatch.setattr(pipe, '_prepare_natives', lambda *a: [])
    monkeypatch.setattr(pipe, '_dock_natives', lambda *a: [])
    monkeypatch.setattr(pipe, '_run_rmsd_validation', lambda *a: [{'rmsd_angstrom': .5}])
    monkeypatch.setattr(pipe, '_merge_rmsd_poses', lambda *a: None)
    assert pipe.run() == 1


def test_affinity_best_rmsd_remains_missing_when_that_pose_failed(make_pipeline, tmp_path, monkeypatch):
    pipe = make_pipeline()
    pipe._natives = [_native_entry()]
    mols = [_fake_ligand_mol(), _fake_ligand_mol()]
    mols[1].SetBoolProp('valid_rmsd', True)
    monkeypatch.setattr(pm, 'read_pdbqt', lambda *a, **kw: mols)

    class Validator:
        def __init__(self, *a, **kw): pass
        def validate(self, block, mol, label):
            valid = mol.HasProp('valid_rmsd')
            return SimpleNamespace(rmsd=.5 if valid else None, status='good' if valid else 'gagal',
                                   method='test', note='')

    monkeypatch.setattr(pm, 'RedockingValidator', Validator)
    run = DockingRunResult('NATIVE_N3_A1', 'R1', 1, 42,
                           poses=[{'mode': 1, 'affinity': -10.}, {'mode': 2, 'affinity': -8.}],
                           output_pdbqt=tmp_path / 'rep1.pdbqt')
    best = pipe._run_rmsd_validation(_context('R1'), [run])[0]
    assert best['mode'] == 2 and best['rmsd_angstrom'] == .5
    assert best['affinity_best_mode'] == 1 and best['rmsd_affinity_best_angstrom'] is None
