"""Test state resume: tulis JSON atomik, salinan input, round-trip konfigurasi, dan pembersihan checkpoint."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from chemflow.config import PipelineConfig
from chemflow.state import RunState, from_rel, read_json, to_rel, write_json_atomic


@pytest.fixture
def excels(tmp_path):
    ligand = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Etanol"], "smiles": ["CCO"]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)
    return ligand, receptor


def test_write_json_atomic_menulis_dan_tanpa_sisa_tmp(tmp_path):
    target = tmp_path / "a" / "b.json"
    write_json_atomic(target, {"x": 1, "nama": "Ω"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1, "nama": "Ω"}
    assert not list(target.parent.glob("*.tmp"))


def test_write_json_atomic_gagal_ganti_file_lama_tetap_utuh(tmp_path, monkeypatch):
    target = tmp_path / "c.json"
    write_json_atomic(target, {"versi": 1})

    def gagal(*args, **kwargs):
        raise PermissionError("dikunci")

    monkeypatch.setattr(os, "replace", gagal)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(PermissionError):
        write_json_atomic(target, {"versi": 2})
    assert read_json(target) == {"versi": 1}


def test_read_json_default_untuk_file_tak_ada_atau_rusak(tmp_path):
    assert read_json(tmp_path / "tidak_ada.json", {"d": 1}) == {"d": 1}
    rusak = tmp_path / "rusak.json"
    rusak.write_text('{"terpotong": ', encoding="utf-8")
    assert read_json(rusak, []) == []


def test_path_relatif_bolak_balik_dan_folder_boleh_pindah(tmp_path):
    base = tmp_path / "out"
    inside = base / "docking" / "R" / "L" / "rep01_out.pdbqt"
    text = to_rel(inside, base)
    assert text == "docking/R/L/rep01_out.pdbqt"
    moved = tmp_path / "dipindah"
    assert from_rel(text, moved) == moved / "docking" / "R" / "L" / "rep01_out.pdbqt"
    outside = tmp_path / "lain" / "x.pdbqt"
    assert from_rel(to_rel(outside, base), base) == outside
    assert to_rel(None, base) is None and from_rel(None, base) is None


def test_config_to_dict_from_dict_round_trip(excels, tmp_path):
    ligand, receptor = excels
    cfg = PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=tmp_path / "out",
                         n_replicates=3, figure_formats=("svg",), plot_max_rows=12, include_native=False,
                         openbabel_path=ligand)
    data = json.loads(json.dumps(cfg.to_dict()))
    again = PipelineConfig.from_dict(data)
    assert again == cfg
    assert isinstance(again.output_dir, Path) and again.figure_formats == ("png", "svg")


def test_config_from_dict_mengabaikan_kunci_asing(excels, tmp_path):
    ligand, receptor = excels
    data = PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=tmp_path / "o").to_dict()
    data["kunci_dari_versi_lain"] = 1
    assert PipelineConfig.from_dict(data).output_dir == (tmp_path / "o").resolve()


def test_config_plot_max_negatif_ditolak(excels):
    ligand, receptor = excels
    with pytest.raises(ValueError, match="plot_max_rows"):
        PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, plot_max_rows=-1)


def test_save_dan_load_config_memakai_salinan_input(excels, tmp_path):
    ligand, receptor = excels
    out = tmp_path / "out"
    cfg = PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out, n_replicates=2)
    state = RunState(out)
    assert not state.exists()
    state.save_config(cfg)
    assert state.exists()

    ligand.unlink()  # file asli hilang: resume tetap jalan dari salinan
    loaded = state.load_config()
    assert loaded.n_replicates == 2
    assert loaded.ligand_excel == (state.inputs_dir / "ligands.xlsx").resolve()
    assert loaded.ligand_excel.exists()


def test_load_config_memakai_folder_output_yang_diberikan(excels, tmp_path):
    ligand, receptor = excels
    original = tmp_path / "out"
    RunState(original).save_config(PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=original))
    moved = tmp_path / "dipindah"
    original.rename(moved)
    assert RunState(moved).load_config().output_dir == moved.resolve()


def test_save_config_saat_resume_mempertahankan_path_asli_dan_menyimpan_override(excels, tmp_path):
    ligand, receptor = excels
    out = tmp_path / "out"
    state = RunState(out)
    state.save_config(PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out))

    resumed = state.load_config()
    resumed.log_level = "DEBUG"
    state.save_config(resumed)

    payload = json.loads(state.config_path.read_text(encoding="utf-8"))
    assert payload["config"]["ligand_excel"] == str(ligand.resolve())
    assert payload["config"]["log_level"] == "DEBUG"
    assert state.load_config().log_level == "DEBUG"


def test_load_config_tanpa_state_pesan_jelas(tmp_path):
    with pytest.raises(FileNotFoundError, match="chemflow run"):
        RunState(tmp_path / "kosong").load_config()


def test_load_config_skema_tidak_cocok(excels, tmp_path):
    ligand, receptor = excels
    out = tmp_path / "out"
    state = RunState(out)
    state.save_config(PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out))
    payload = json.loads(state.config_path.read_text(encoding="utf-8"))
    payload["schema"] = 999
    state.config_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Skema"):
        state.load_config()


def test_progress_dan_is_unfinished(excels, tmp_path):
    ligand, receptor = excels
    out = tmp_path / "out"
    state = RunState(out)
    assert state.is_unfinished() is False
    state.save_config(PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out))
    state.update_progress("docking")
    assert state.is_unfinished() is True
    assert state.read_progress()["stage"] == "docking"
    state.update_progress("selesai", finished=True)
    assert state.is_unfinished() is False


def test_clear_checkpoints_hanya_menghapus_checkpoint(tmp_path):
    out = tmp_path / "out"
    state = RunState(out)
    keep = [out / "docking" / "R" / "L" / "rep01_out.pdbqt", out / "ligands" / "L" / "L.pdbqt"]
    drop = [out / "docking" / "R" / "L" / "rep01.json", out / "ligands" / "L" / "prepared.json",
            out / "receptors" / "R" / "prepared.json", state.ligands_path, state.admet_cache_path,
            state.progress_path]
    for path in keep + drop:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    state.clear_checkpoints()
    assert all(p.exists() for p in keep)
    assert not any(p.exists() for p in drop)


def test_save_config_menyalin_file_admet_dan_resume_memakainya(excels, tmp_path):
    ligand, receptor = excels
    admet = tmp_path / "admet.csv"
    admet.write_text("smiles,hERG\nCCO,0.1\n", encoding="utf-8")
    out = tmp_path / "out"
    state = RunState(out)
    state.save_config(PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out, admet_file=admet))

    admet.unlink()
    loaded = state.load_config()
    assert loaded.admet_file == (state.inputs_dir / "admet.csv").resolve()
    assert loaded.admet_file.read_text(encoding="utf-8").startswith("smiles")
