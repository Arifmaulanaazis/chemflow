"""
Test OpenBabelConverter tanpa memanggil obabel asli. Subprocess di-mock
supaya test ini jalan di CI mana pun tanpa perlu OpenBabel terpasang.
Yang divalidasi: konstruksi argv (-i/-o/-O/-h/-xr) dan penanganan error/output-kosong.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from chemflow.chem import mol_converter as mc


@pytest.fixture
def fake_obabel(tmp_path, monkeypatch):
    """Sediakan 'executable' obabel palsu (cukup file yang exist) + override resolve."""
    fake_exe = tmp_path / "obabel_fake"
    fake_exe.write_text("dummy")
    return fake_exe


def test_ligand_conversion_pakai_flag_h_dan_muatan_gasteiger(tmp_path, fake_obabel, monkeypatch):
    captured = {}

    def fake_run_capture(cmd, cwd=None, timeout=None):
        captured["cmd"] = cmd
        # cari argumen -O<path>
        o_arg = next(c for c in cmd if c.startswith("-O"))
        out_file = Path(o_arg[2:])
        out_file.write_text("PDBQT dummy content\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mc, "run_capture", fake_run_capture)

    converter = mc.OpenBabelConverter(openbabel_path=fake_obabel)
    pdb_in = tmp_path / "lig.pdb"
    pdb_in.write_text("dummy pdb\n")
    pdbqt_out = tmp_path / "lig.pdbqt"

    result = converter.pdb_to_pdbqt(pdb_in, pdbqt_out, is_receptor=False)
    assert result == pdbqt_out
    assert "-h" in captured["cmd"]
    assert "-xr" not in captured["cmd"]
    index = captured["cmd"].index("--partialcharge")
    assert captured["cmd"][index + 1] == "gasteiger"
    assert "-i" in captured["cmd"] and "pdb" in captured["cmd"]
    assert "-o" in captured["cmd"] and "pdbqt" in captured["cmd"]


def test_receptor_conversion_pakai_flag_xr_dan_strip_torsion_tags(tmp_path, fake_obabel, monkeypatch):
    captured = {}

    def fake_run_capture(cmd, cwd=None, timeout=None):
        captured["cmd"] = cmd
        o_arg = next(c for c in cmd if c.startswith("-O"))
        out_file = Path(o_arg[2:])
        out_file.write_text("ATOM      1  N   ALA A   1\nROOT\nENDROOT\nTORSDOF 0\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mc, "run_capture", fake_run_capture)

    converter = mc.OpenBabelConverter(openbabel_path=fake_obabel)
    pdb_in = tmp_path / "rec.pdb"
    pdb_in.write_text("dummy pdb\n")
    pdbqt_out = tmp_path / "rec.pdbqt"

    converter.pdb_to_pdbqt(pdb_in, pdbqt_out, is_receptor=True)
    assert "-xr" in captured["cmd"]
    assert "--partialcharge" not in captured["cmd"]
    content = pdbqt_out.read_text()
    assert "ROOT" not in content
    assert "TORSDOF" not in content
    assert "ATOM" in content


def test_output_kosong_raise_value_error(tmp_path, fake_obabel, monkeypatch):
    def fake_run_capture(cmd, cwd=None, timeout=None):
        return SimpleNamespace(returncode=0, stdout="", stderr="")  # tak menulis file apa pun

    monkeypatch.setattr(mc, "run_capture", fake_run_capture)

    converter = mc.OpenBabelConverter(openbabel_path=fake_obabel)
    pdb_in = tmp_path / "lig.pdb"
    pdb_in.write_text("dummy\n")

    with pytest.raises(ValueError, match="output kosong"):
        converter.pdb_to_pdbqt(pdb_in, tmp_path / "lig.pdbqt", is_receptor=False)


def test_exit_code_nonzero_raise_value_error(tmp_path, fake_obabel, monkeypatch):
    def fake_run_capture(cmd, cwd=None, timeout=None):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(mc, "run_capture", fake_run_capture)

    converter = mc.OpenBabelConverter(openbabel_path=fake_obabel)
    pdb_in = tmp_path / "lig.pdb"
    pdb_in.write_text("dummy\n")

    with pytest.raises(ValueError, match="boom"):
        converter.pdb_to_pdbqt(pdb_in, tmp_path / "lig.pdbqt", is_receptor=False)


def test_resolve_openbabel_tidak_ditemukan_raise():
    with pytest.raises(FileNotFoundError):
        mc.resolve_openbabel_executable(Path("path/tidak/ada/obabel.exe"))


def test_explicit_path_saved_and_reused_without_search(tmp_path, monkeypatch):
    exe = tmp_path / 'obabel.exe'
    exe.touch()
    assert mc.resolve_openbabel_executable(exe) == str(exe.resolve())
    monkeypatch.setattr(mc.shutil, 'which', lambda name: pytest.fail('Cache must avoid PATH lookup'))
    monkeypatch.setattr(mc, '_openbabel_candidates', lambda: pytest.fail('Cache must avoid discovery'))
    assert mc.resolve_openbabel_executable() == str(exe.resolve())


def test_stale_cache_falls_back_to_installation(tmp_path, monkeypatch):
    old = tmp_path / 'old.exe'
    old.touch()
    mc.resolve_openbabel_executable(old)
    old.unlink()
    installed = tmp_path / 'OpenBabel-3.1.1' / 'obabel.exe'
    installed.parent.mkdir()
    installed.touch()
    monkeypatch.setattr(mc.shutil, 'which', lambda name: None)
    monkeypatch.setattr(mc, '_openbabel_candidates', lambda: iter([installed]))
    assert mc.resolve_openbabel_executable() == str(installed.resolve())
    assert str(installed).replace('\\', '\\\\') in mc._openbabel_cache_file().read_text()


def test_corrupt_cache_and_missing_executable(tmp_path, monkeypatch):
    cache = mc._openbabel_cache_file()
    cache.parent.mkdir(parents=True)
    cache.write_text('{broken')
    monkeypatch.setattr(mc.shutil, 'which', lambda name: None)
    monkeypatch.setattr(mc, '_openbabel_candidates', lambda: iter(()))
    with pytest.raises(FileNotFoundError, match='lokasi instalasi umum'):
        mc.resolve_openbabel_executable()


def test_invalid_override_does_not_use_cached_executable(tmp_path):
    exe = tmp_path / 'obabel.exe'
    exe.touch()
    mc.resolve_openbabel_executable(exe)
    with pytest.raises(FileNotFoundError, match='path yang diberikan'):
        mc.resolve_openbabel_executable(tmp_path / 'missing.exe')
