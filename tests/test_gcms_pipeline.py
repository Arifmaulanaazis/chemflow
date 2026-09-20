"""Test integrasi GC-MS opsional ke konfigurasi, pipeline, dan CLI 'run': tidak boleh mengganggu alur utama."""

import json
import logging

import pandas as pd
import pytest

import chemflow.cli as cli
from chemflow import Pipeline, PipelineConfig
from tests.gcms_data import make_trace, synthetic_peaks, write_two_column_csv


@pytest.fixture
def inputs(tmp_path):
    ligand = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Etanol"], "smiles": ["CCO"]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)
    data = tmp_path / "gcms"
    data.mkdir()
    for k in (1, 2):
        write_two_column_csv(data / f"S{k}.csv", *make_trace(synthetic_peaks(), seed=k))
    return ligand, receptor, tmp_path / "out", data


def _config(inputs, **overrides):
    ligand, receptor, out, _ = inputs
    return PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out, openbabel_path=ligand,
                          show_progress=False, **overrides)


def test_gcms_mati_secara_bawaan(inputs):
    cfg = _config(inputs)
    assert cfg.gcms_data == () and cfg.gcms_groups is None and cfg.gcms_library is None


def test_gcms_bolak_balik_lewat_dict_json(inputs):
    data = inputs[3]
    cfg = _config(inputs, gcms_data=(data,), gcms_groups=inputs[0], gcms_library=inputs[1])
    payload = json.loads(json.dumps(cfg.to_dict()))
    assert payload["gcms_data"] == [str(data)]
    again = PipelineConfig.from_dict(payload)
    assert again.gcms_data == (data,) and again.gcms_groups == cfg.gcms_groups and again.gcms_library == cfg.gcms_library


def test_gcms_data_salah_ketik_gagal_cepat(inputs, tmp_path):
    with pytest.raises(FileNotFoundError, match="Data GC-MS tidak ditemukan"):
        _config(inputs, gcms_data=(tmp_path / "typo",))
    _config(inputs, gcms_data=(str(tmp_path / "gcms" / "*.csv"),))


def test_resume_tidak_gagal_bila_data_gcms_sudah_dipindah(inputs, caplog):
    payload = _config(inputs, gcms_data=(inputs[3],)).to_dict()
    payload["gcms_data"] = [str(inputs[3]), str(inputs[3] / "hilang")]
    with caplog.at_level(logging.WARNING, logger="chemflow"):
        cfg = PipelineConfig.from_dict(payload)
    assert cfg.gcms_data == (inputs[3],) and "tidak ditemukan lagi" in caplog.text


def test_tahap_gcms_menulis_hasil_di_folder_output(inputs):
    pipeline = Pipeline(_config(inputs, gcms_data=(inputs[3],), figure_dpi=72))
    pipeline._run_gcms()
    assert (pipeline.cfg.output_dir / "gcms" / "analisis_gcms.xlsx").exists()


def test_kegagalan_gcms_hanya_peringatan_bukan_error(inputs, tmp_path, caplog):
    kosong = tmp_path / "kosong"
    kosong.mkdir()
    pipeline = Pipeline(_config(inputs, gcms_data=(kosong,)))
    pipeline.log.propagate = True
    with caplog.at_level(logging.WARNING, logger="chemflow"):
        pipeline._run_gcms()
    assert "Analisis GC-MS dilewati" in caplog.text


def test_parser_run_opsi_gcms():
    base = ["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx"]
    args = cli.build_parser().parse_args(base)
    assert args.gcms is None and args.gcms_groups is None and args.gcms_library is None
    args = cli.build_parser().parse_args(base + ["--gcms", "d1", "d2", "--gcms-groups", "g.csv", "--gcms-library", "l.csv"])
    assert [str(p) for p in args.gcms] == ["d1", "d2"] and str(args.gcms_groups) == "g.csv" and str(args.gcms_library) == "l.csv"


def test_run_meneruskan_opsi_gcms_ke_config(inputs, monkeypatch):
    ligand, receptor, out, data = inputs
    captured = {}

    class FakePipeline:
        def __init__(self, config):
            captured["config"] = config

        def run(self):
            return 0

    monkeypatch.setattr(cli, "Pipeline", FakePipeline)
    code = cli.main(["run", "--ligands", str(ligand), "--receptors", str(receptor), "--output", str(out),
                     "--openbabel-path", str(ligand), "--gcms", str(data), "--no-progress"])
    assert code == 0 and captured["config"].gcms_data == (data,)
