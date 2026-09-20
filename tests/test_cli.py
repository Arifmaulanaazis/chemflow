"""Test argparse CLI chemflow: subperintah init/run/list-vina-versions."""

import pandas as pd
import pytest

from chemflow.cli import build_parser, main


def test_parser_butuh_subperintah():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_init_default():
    parser = build_parser()
    args = parser.parse_args(["init"])
    assert args.command == "init"
    assert args.format == "both"
    assert args.skip_check is False


def test_parser_init_custom_output():
    parser = build_parser()
    args = parser.parse_args(["init", "--output", "myfolder", "--format", "tidy", "--skip-check"])
    assert str(args.output) == "myfolder"
    assert args.format == "tidy"
    assert args.skip_check is True


def test_parser_run_butuh_ligands_dan_receptors():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run"])


def test_parser_run_lengkap():
    parser = build_parser()
    args = parser.parse_args(["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx", "--exhaustiveness", "16"])
    assert args.command == "run"
    assert str(args.ligands) == "a.xlsx"
    assert args.exhaustiveness == 16


def test_parser_run_merge_mode_default_best():
    parser = build_parser()
    args = parser.parse_args(["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx"])
    assert args.merge_mode == "best"


def test_parser_run_merge_mode_all():
    parser = build_parser()
    args = parser.parse_args(["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx", "--merge-mode", "all"])
    assert args.merge_mode == "all"


def test_parser_run_merge_mode_invalid_ditolak():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx", "--merge-mode", "salah"])


def test_parser_similarity_lengkap():
    parser = build_parser()
    args = parser.parse_args(["similarity", "--output", "hasil"])
    assert args.command == "similarity"
    assert str(args.output) == "hasil"
    assert args.interactions_dir is None
    assert args.interaction_suffix == "_interaksi.xlsx"
    assert args.result_filename == "similaritas_interaksi.xlsx"


def test_parser_similarity_butuh_output():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["similarity"])


def test_parser_similarity_custom_interactions_dir_dan_suffix():
    parser = build_parser()
    args = parser.parse_args([
        "similarity", "--output", "hasil", "--interactions-dir", "interaksi_custom",
        "--interaction-suffix", "_bio.xlsx",
    ])
    assert str(args.interactions_dir) == "interaksi_custom"
    assert args.interaction_suffix == "_bio.xlsx"


def test_parser_run_admet_file_dan_opsi_gambar():
    parser = build_parser()
    args = parser.parse_args([
        "run", "--ligands", "a.xlsx", "--receptors", "b.xlsx", "--admet-file", "admet.csv",
        "--dpi", "600", "--figure-formats", "png", "svg",
    ])
    assert str(args.admet_file) == "admet.csv"
    assert args.dpi == 600
    assert args.figure_formats == ["png", "svg"]


def test_parser_run_default_tanpa_admet_file():
    parser = build_parser()
    args = parser.parse_args(["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx"])
    assert args.admet_file is None
    assert args.dpi == 300


def test_parser_similarity_opsi_plot():
    parser = build_parser()
    args = parser.parse_args(["similarity", "--output", "hasil", "--no-plots", "--figure-formats", "pdf"])
    assert args.no_plots is True
    assert args.figure_formats == ["pdf"]


def test_parser_list_vina_versions():
    parser = build_parser()
    args = parser.parse_args(["list-vina-versions"])
    assert args.command == "list-vina-versions"


def test_parser_receptor_config_tanpa_opsi():
    args = build_parser().parse_args(["receptor-config"])
    assert args.command == "receptor-config"
    assert vars(args) == {"command": "receptor-config"}


@pytest.mark.parametrize("extra", [["--output", "x"], ["--pdb", "6LU7"], ["--receptors", "a.xlsx"]])
def test_parser_receptor_config_menolak_opsi_lain(extra):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["receptor-config", *extra])


def test_main_receptor_config_butuh_terminal_interaktif(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(["receptor-config"]) == 1
    assert "terminal interaktif" in capsys.readouterr().out


def test_main_receptor_config_menjalankan_alur_interaktif(monkeypatch):
    import sys

    from chemflow.io import receptor_config

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(receptor_config, "run_receptor_config", lambda: 0)
    assert main(["receptor-config"]) == 0


def test_main_receptor_config_dibatalkan_pengguna(monkeypatch, capsys):
    import sys

    from chemflow.io import receptor_config

    def batal():
        raise KeyboardInterrupt

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(receptor_config, "run_receptor_config", batal)
    assert main(["receptor-config"]) == 1
    assert "Dibatalkan" in capsys.readouterr().out


def test_main_init_membuat_template(tmp_path, monkeypatch, capsys):
    out_dir = tmp_path / "contoh"
    ret = main(["init", "--output", str(out_dir), "--skip-check"])
    assert ret == 0
    assert (out_dir / "ligan_contoh_tidy.xlsx").exists()
    assert (out_dir / "ligan_contoh_wide.xlsx").exists()
    assert (out_dir / "reseptor_contoh.xlsx").exists()

    captured = capsys.readouterr()
    assert "Template Excel dibuat" in captured.out


def test_main_init_format_tidy_saja(tmp_path):
    out_dir = tmp_path / "contoh"
    ret = main(["init", "--output", str(out_dir), "--format", "tidy", "--skip-check"])
    assert ret == 0
    assert (out_dir / "ligan_contoh_tidy.xlsx").exists()
    assert not (out_dir / "ligan_contoh_wide.xlsx").exists()
    assert (out_dir / "reseptor_contoh.xlsx").exists()


def test_main_similarity_output_belum_pernah_run(tmp_path, capsys):
    ret = main(["similarity", "--output", str(tmp_path / "belum_ada")])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Gagal" in captured.out


def test_main_similarity_end_to_end(tmp_path, capsys):
    import json

    from openpyxl import Workbook

    output_dir = tmp_path / "hasil"
    complex_dir = output_dir / "complexes" / "6LU7"
    complex_dir.mkdir(parents=True)

    native_pdb = complex_dir / "NATIVE_ASP_X1_complex.pdb"
    native_pdb.write_text("REMARK stub\n")
    native_pdb.with_suffix(".json").write_text(json.dumps({
        "ligand_name": "Celecoxib", "ligand_code": "", "ligand_chain": "X",
        "ligand_resname": "ASP", "is_native": True,
    }), encoding="utf-8")

    test_pdb = complex_dir / "Aspirin_complex.pdb"
    test_pdb.write_text("REMARK stub\n")
    test_pdb.with_suffix(".json").write_text(json.dumps({
        "ligand_name": "Aspirin", "ligand_code": "", "ligand_chain": "X",
        "ligand_resname": "ASP", "is_native": False,
    }), encoding="utf-8")

    interactions_dir = output_dir / "interaksi" / "6LU7"
    interactions_dir.mkdir(parents=True)

    def _write(path, from_spec, to_spec):
        wb = Workbook()
        ws = wb.active
        ws.append([f"{from_spec} - {to_spec}", "Yes", "0 255 0", "Ligand Non-bond Monitor", 1,
                   "Hydrogen Bond", "Conventional Hydrogen Bond", from_spec, "H-Donor", to_spec, "H-Acceptor"])
        wb.save(path)

    _write(interactions_dir / "NATIVE_ASP_X1_complex_interaksi.xlsx", "A:HIS75:NE2", "X:ASP1:O1")
    _write(interactions_dir / "Aspirin_complex_interaksi.xlsx", "A:HIS75:NE2", "X:ASP1:O1")

    ret = main(["similarity", "--output", str(output_dir)])
    assert ret == 0

    result_path = output_dir / "similaritas_interaksi.xlsx"
    assert result_path.exists()

    df = pd.read_excel(result_path)
    assert df.iloc[0]["ligand"] == "Aspirin"
    assert df.iloc[0]["overall_similarity_pct"] == 100.0

    captured = capsys.readouterr()
    assert "1 pasangan ligan-reseptor" in captured.out


def test_parser_run_opsi_baru_default():
    args = build_parser().parse_args(["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx"])
    assert args.no_native is False and args.box_padding == 8.0 and args.default_box_size == 20.0
    assert args.plot_max_rows == 30 and args.plot_max_cols == 20


def test_parser_run_opsi_baru_diisi():
    args = build_parser().parse_args(["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx", "--no-native",
                                      "--box-padding", "6", "--plot-max-rows", "0", "--plot-max-cols", "12"])
    assert args.no_native is True and args.box_padding == 6.0
    assert args.plot_max_rows == 0 and args.plot_max_cols == 12


def test_parser_similarity_opsi_potong_plot():
    args = build_parser().parse_args(["similarity", "--output", "hasil", "--plot-max-rows", "10"])
    assert args.plot_max_rows == 10 and args.plot_max_cols == 20


def test_parser_resume_butuh_output():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["resume"])


def test_parser_resume_lengkap():
    args = build_parser().parse_args(["resume", "--output", "hasil", "--no-progress", "--log-level", "DEBUG",
                                      "--openbabel-path", "ob.exe", "--vina-executable", "vina.exe"])
    assert args.command == "resume" and str(args.output) == "hasil" and args.no_progress is True
    assert args.log_level == "DEBUG" and str(args.openbabel_path) == "ob.exe" and str(args.vina_executable) == "vina.exe"


def test_parser_resume_tidak_menerima_setelan_run():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["resume", "--output", "hasil", "--exhaustiveness", "16"])


def test_main_resume_folder_tanpa_state(tmp_path, capsys):
    assert main(["resume", "--output", str(tmp_path / "kosong")]) == 1
    out = capsys.readouterr().out
    assert "Gagal" in out and "chemflow run" in out


def _state_folder(tmp_path, finished=False):
    from chemflow.config import PipelineConfig
    from chemflow.state import RunState

    ligand = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Etanol"], "smiles": ["CCO"]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)
    out = tmp_path / "hasil"
    state = RunState(out)
    state.save_config(PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out, n_replicates=2))
    state.update_progress("docking" if not finished else "selesai", finished=finished)
    return out


def test_main_resume_menjalankan_pipeline_dengan_resume_dan_override(tmp_path, monkeypatch, capsys):
    import chemflow.cli as cli

    out = _state_folder(tmp_path)
    captured = {}

    class _FakePipeline:
        def __init__(self, config, resume=False):
            captured.update(config=config, resume=resume)

        def run(self):
            return 0

    monkeypatch.setattr(cli, "Pipeline", _FakePipeline)
    ret = main(["resume", "--output", str(out), "--no-progress", "--log-level", "WARNING",
                "--openbabel-path", str(tmp_path / "ob.exe")])
    assert ret == 0 and captured["resume"] is True
    config = captured["config"]
    assert config.n_replicates == 2 and config.show_progress is False and config.log_level == "WARNING"
    assert config.openbabel_path == (tmp_path / "ob.exe").resolve()
    assert config.output_dir == out.resolve()
    assert "docking" in capsys.readouterr().out


def test_main_resume_run_selesai_memberi_tahu_hanya_regenerasi(tmp_path, monkeypatch, capsys):
    import chemflow.cli as cli

    out = _state_folder(tmp_path, finished=True)
    monkeypatch.setattr(cli, "Pipeline", lambda config, resume=False: type("P", (), {"run": lambda self: 0})())
    assert main(["resume", "--output", str(out)]) == 0
    assert "sudah selesai" in capsys.readouterr().out


def test_main_run_meneruskan_opsi_baru_ke_config(tmp_path, monkeypatch):
    import chemflow.cli as cli

    ligand = tmp_path / "l.xlsx"
    pd.DataFrame({"name": ["Etanol"], "smiles": ["CCO"]}).to_excel(ligand, index=False)
    receptor = tmp_path / "r.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)
    seen = {}

    class _FakePipeline:
        def __init__(self, config, resume=False):
            seen.update(config=config, resume=resume)

        def run(self):
            return 0

    monkeypatch.setattr(cli, "Pipeline", _FakePipeline)
    assert main(["run", "--ligands", str(ligand), "--receptors", str(receptor), "--output", str(tmp_path / "o"),
                 "--no-native", "--box-padding", "5", "--plot-max-rows", "12", "--plot-max-cols", "0"]) == 0
    config = seen["config"]
    assert seen["resume"] is False and config.include_native is False and config.box_padding == 5.0
    assert config.plot_max_rows == 12 and config.plot_max_cols == 0
