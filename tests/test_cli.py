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
