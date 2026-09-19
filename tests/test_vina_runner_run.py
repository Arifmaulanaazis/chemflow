"""Test VinaRunner.run(). subprocess (stream_process) di-mock, tidak memanggil Vina asli."""

from pathlib import Path

import pytest

from chemflow.docking import vina_runner as vr
from chemflow.docking.grid_box import GridBox

_SUCCESS_OUTPUT = [
    "AutoDock Vina v1.2.5\n",
    "mode |   affinity | dist from best mode\n",
    "-----+------------+----------+----------\n",
    "   1       -7.234      0.000      0.000\n",
    "   2       -6.500      1.500      3.000\n",
]


@pytest.fixture
def grid_box():
    return GridBox.from_manual(0, 0, 0, 20, 20, 20)


def test_run_sukses_parse_poses_dan_tulis_log(tmp_path, grid_box, monkeypatch):
    monkeypatch.setattr(vr, "stream_process", lambda cmd, on_line=None, echo=False: (0, _SUCCESS_OUTPUT))

    runner = vr.VinaRunner("fake_vina_exe")
    poses = runner.run(
        receptor_pdbqt=tmp_path / "rec.pdbqt", ligand_pdbqt=tmp_path / "lig.pdbqt",
        output_pdbqt=tmp_path / "out.pdbqt", log_file=tmp_path / "run.log", grid_box=grid_box,
    )

    assert len(poses) == 2
    assert poses[0]["affinity"] == -7.234
    log_path = tmp_path / "run.log"
    assert log_path.exists()
    assert "AutoDock Vina" in log_path.read_text()


def test_run_exit_nonzero_raise_dengan_tail_log(tmp_path, grid_box, monkeypatch):
    monkeypatch.setattr(vr, "stream_process", lambda cmd, on_line=None, echo=False: (1, ["ERROR: bad input\n"]))

    runner = vr.VinaRunner("fake_vina_exe")
    with pytest.raises(RuntimeError, match="ERROR: bad input"):
        runner.run(
            receptor_pdbqt=tmp_path / "rec.pdbqt", ligand_pdbqt=tmp_path / "lig.pdbqt",
            output_pdbqt=tmp_path / "out.pdbqt", log_file=tmp_path / "run.log", grid_box=grid_box,
        )


def test_run_menyertakan_seed_dan_extra_args(tmp_path, grid_box, monkeypatch):
    captured = {}

    def fake_stream(cmd, on_line=None, echo=False):
        captured["cmd"] = cmd
        return 0, _SUCCESS_OUTPUT

    monkeypatch.setattr(vr, "stream_process", fake_stream)

    runner = vr.VinaRunner("fake_vina_exe")
    runner.run(
        receptor_pdbqt=tmp_path / "rec.pdbqt", ligand_pdbqt=tmp_path / "lig.pdbqt",
        output_pdbqt=tmp_path / "out.pdbqt", log_file=tmp_path / "run.log", grid_box=grid_box,
        seed=42, extra_args=["--cpu", "1"],
    )
    assert "--seed" in captured["cmd"] and "42" in captured["cmd"]
    assert "--cpu" in captured["cmd"] and "1" in captured["cmd"]


def test_run_raise_jika_gridbox_belum_dikonkretkan(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "stream_process", lambda cmd, on_line=None, echo=False: (0, _SUCCESS_OUTPUT))
    runner = vr.VinaRunner("fake_vina_exe")
    auto_box = GridBox(center_x=0, center_y=0, center_z=0)  # size masih None
    with pytest.raises(ValueError, match="belum dikonkretkan"):
        runner.run(
            receptor_pdbqt=tmp_path / "rec.pdbqt", ligand_pdbqt=tmp_path / "lig.pdbqt",
            output_pdbqt=tmp_path / "out.pdbqt", log_file=tmp_path / "run.log", grid_box=auto_box,
        )


def test_resolve_vina_executable_prioritas_explicit_path():
    from chemflow.docking.vina_manager import VinaReleaseManager

    manager = VinaReleaseManager()
    resolved = vr.resolve_vina_executable(manager, explicit_path=Path("C:/manual/vina.exe"))
    assert resolved == Path("C:/manual/vina.exe")
