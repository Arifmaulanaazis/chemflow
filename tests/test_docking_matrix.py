"""Test DockingOrchestrator & compute_replicate_stats. VinaRunner di-mock total."""

from pathlib import Path

import pytest

from chemflow.docking.docking_matrix import (
    DockingOrchestrator, ReceptorDockingTarget, compute_replicate_stats,
)
from chemflow.docking.grid_box import GridBox


class _FakeVinaRunner:
    """VinaRunner palsu: kembalikan pose sukses utk ligan tertentu, raise utk yang lain."""

    def __init__(self, fail_for=None, affinities=None):
        self._fail_for = fail_for or set()
        self._affinities = affinities or {}

    def run(self, receptor_pdbqt, ligand_pdbqt, output_pdbqt, log_file, grid_box, **kwargs):
        name = ligand_pdbqt.stem
        if name in self._fail_for:
            raise RuntimeError(f"Vina gagal (simulasi) untuk {name}")
        affinity = self._affinities.get(name, -5.0)
        return [{"mode": 1, "affinity": affinity, "rmsd_lb": 0.0, "rmsd_ub": 0.0}]


def _target(key="REC1"):
    return ReceptorDockingTarget(
        key=key, pdb_code=key, receptor_pdbqt=Path(f"{key}.pdbqt"),
        receptor_clean_pdb=Path(f"{key}_clean.pdb"),
        grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20),
    )


def test_run_matrix_semua_sukses(tmp_path):
    runner = _FakeVinaRunner(affinities={"LigA": -7.0, "LigB": -5.0})
    orchestrator = DockingOrchestrator(runner)
    ligands = {"LigA": Path("LigA.pdbqt"), "LigB": Path("LigB.pdbqt")}

    results = orchestrator.run_matrix(ligands, [_target()], tmp_path, n_replicates=1, show_progress=False)
    assert len(results) == 2
    assert all(r.success for r in results)
    affinities = {r.ligand_name: r.best_affinity for r in results}
    assert affinities == {"LigA": -7.0, "LigB": -5.0}


def test_run_matrix_satu_ligan_gagal_tidak_menghentikan_lain(tmp_path):
    runner = _FakeVinaRunner(fail_for={"LigB"})
    orchestrator = DockingOrchestrator(runner)
    ligands = {"LigA": Path("LigA.pdbqt"), "LigB": Path("LigB.pdbqt")}

    results = orchestrator.run_matrix(ligands, [_target()], tmp_path, n_replicates=1, show_progress=False)
    assert len(results) == 2
    by_name = {r.ligand_name: r for r in results}
    assert by_name["LigA"].success is True
    assert by_name["LigB"].success is False
    assert by_name["LigB"].error is not None


def test_run_matrix_show_progress_default_true_tidak_crash(tmp_path):
    runner = _FakeVinaRunner()
    orchestrator = DockingOrchestrator(runner)
    ligands = {"LigA": Path("LigA.pdbqt")}

    results = orchestrator.run_matrix(ligands, [_target()], tmp_path, n_replicates=1)
    assert len(results) == 1
    assert results[0].success is True


def test_run_matrix_multi_replikat_menghasilkan_seed_berbeda(tmp_path):
    runner = _FakeVinaRunner()
    orchestrator = DockingOrchestrator(runner)
    ligands = {"LigA": Path("LigA.pdbqt")}

    results = orchestrator.run_matrix(ligands, [_target()], tmp_path, n_replicates=3, base_seed=100)
    seeds = [r.seed for r in results]
    assert seeds == [100, 101, 102]


def test_compute_replicate_stats_mean_std():
    from chemflow.docking.docking_matrix import DockingRunResult

    results = [
        DockingRunResult("LigA", "REC1", 1, 1, poses=[{"mode": 1, "affinity": -6.0}]),
        DockingRunResult("LigA", "REC1", 2, 2, poses=[{"mode": 1, "affinity": -6.2}]),
        DockingRunResult("LigA", "REC1", 3, 3, poses=[{"mode": 1, "affinity": -5.8}]),
    ]
    stats = compute_replicate_stats(results)
    assert len(stats) == 1
    row = stats[0]
    assert row["ligand"] == "LigA"
    assert row["n_replicates_success"] == 3
    assert row["affinity_mean"] == pytest.approx(-6.0, abs=0.01)
    assert row["affinity_best"] == pytest.approx(-6.2)
    assert row["affinity_std"] > 0


def test_compute_replicate_stats_mengabaikan_run_gagal():
    from chemflow.docking.docking_matrix import DockingRunResult

    results = [
        DockingRunResult("LigA", "REC1", 1, 1, poses=[{"mode": 1, "affinity": -6.0}]),
        DockingRunResult("LigA", "REC1", 2, 2, error="gagal"),
    ]
    stats = compute_replicate_stats(results)
    assert stats[0]["n_replicates_success"] == 1
