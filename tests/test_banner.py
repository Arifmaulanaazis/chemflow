"""Test header ASCII-art yang dicetak setiap kali CLI chemflow dijalankan."""

import io
import sys
from types import SimpleNamespace

import pytest

import chemflow
from chemflow import cli
from chemflow.banner import _LOGO_LINES, print_banner, render_banner


def test_render_banner_memuat_logo_versi_dan_tagline():
    banner = render_banner()
    for line in _LOGO_LINES:
        assert line in banner
    assert f"chemflow v{chemflow.__version__}" in banner
    assert "Skrining virtual senyawa obat otomatis" in banner


def test_render_banner_ascii_murni_dan_muat_di_80_kolom():
    banner = render_banner()
    assert banner.isascii()
    assert max(len(line) for line in banner.splitlines()) <= 80


def test_render_banner_tanpa_spasi_ujung_baris():
    for line in render_banner().splitlines():
        assert line == line.rstrip()


def test_logo_tanpa_baris_kosong_di_awal_dan_akhir():
    assert _LOGO_LINES[0].strip()
    assert _LOGO_LINES[-1].strip()
    assert all(line.strip() for line in _LOGO_LINES)


def test_print_banner_ke_stream_khusus():
    buf = io.StringIO()
    print_banner(buf)
    assert buf.getvalue() == render_banner() + "\n\n"


def test_print_banner_default_ke_stdout(capsys):
    print_banner()
    assert capsys.readouterr().out == render_banner() + "\n\n"


def test_main_help_menampilkan_header(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith(render_banner())
    assert "usage: chemflow" in out


def test_main_tanpa_subperintah_tetap_menampilkan_header(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
    assert capsys.readouterr().out.startswith(render_banner())


def test_main_init_menampilkan_header_sebelum_keluaran(tmp_path, capsys):
    assert cli.main(["init", "--output", str(tmp_path / "contoh"), "--skip-check"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(render_banner())
    assert out.index("Template Excel dibuat") > len(render_banner())


def test_main_receptor_config_menampilkan_header(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert cli.main(["receptor-config"]) == 1
    assert capsys.readouterr().out.startswith(render_banner())


def test_main_similarity_menampilkan_header(tmp_path, capsys):
    assert cli.main(["similarity", "--output", str(tmp_path / "belum_ada")]) == 1
    assert capsys.readouterr().out.startswith(render_banner())


def test_main_list_vina_versions_menampilkan_header(monkeypatch, capsys):
    stub = SimpleNamespace(list_compatible=lambda: [])
    monkeypatch.setattr(cli, "VinaReleaseManager", lambda: stub)
    assert cli.main(["list-vina-versions"]) == 0
    assert capsys.readouterr().out.startswith(render_banner())


def test_main_run_menampilkan_header(tmp_path, monkeypatch, capsys):
    ligands, receptors = tmp_path / "ligan.xlsx", tmp_path / "reseptor.xlsx"
    ligands.touch()
    receptors.touch()
    monkeypatch.setattr(cli, "Pipeline", lambda config: SimpleNamespace(run=lambda: 0))
    assert cli.main(["run", "--ligands", str(ligands), "--receptors", str(receptors)]) == 0
    assert capsys.readouterr().out.startswith(render_banner())


def test_header_hanya_dicetak_sekali_per_pemanggilan(tmp_path, capsys):
    cli.main(["init", "--output", str(tmp_path / "contoh"), "--skip-check"])
    assert capsys.readouterr().out.count(_LOGO_LINES[0]) == 1
