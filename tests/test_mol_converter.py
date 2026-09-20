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
