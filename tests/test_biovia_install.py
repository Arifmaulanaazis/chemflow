"""Test deteksi instalasi BIOVIA dan lingkungan peluncurannya (registry dan folder disimulasikan)."""

import os
import subprocess

import pytest

from chemflow.interaction.biovia_install import BioviaLocator

APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"


def _install(base, year, with_exe=True, with_bin=True):
    folder = base / f"Discovery Studio {year}"
    (folder / "lib").mkdir(parents=True)
    if with_bin:
        (folder / "bin").mkdir()
        if with_exe:
            (folder / "bin" / f"DiscoveryStudio{year}.exe").write_text("x")
    return folder


def _locator(base_dirs, registry=None, keys=None):
    return BioviaLocator(base_dirs=base_dirs, registry=lambda key: (registry or {}).get(key),
                         registry_keys=lambda key: list(keys or []))


def test_memilih_tahun_terbaru_secara_numerik(tmp_path):
    for year in (2021, 2025, 9):
        _install(tmp_path, year)
    locator = _locator([tmp_path])
    assert [i.year for i in locator.installations()] == [2025, 2021]      # "Discovery Studio 9" bukan format tahun
    assert locator.find_executable().name == "DiscoveryStudio2025.exe"


def test_folder_tanpa_bin_atau_tanpa_exe_diabaikan(tmp_path):
    _install(tmp_path, 2025, with_bin=False)      # sisa instalasi gagal: hanya lib dan share
    _install(tmp_path, 2023, with_exe=False)
    _install(tmp_path, 2021)
    assert _locator([tmp_path]).find_executable().name == "DiscoveryStudio2021.exe"


def test_tidak_ada_instalasi_mengembalikan_none(tmp_path):
    assert _locator([tmp_path / "kosong"]).find_executable() is None


def test_registry_app_paths_ditemukan_walau_folder_tidak_standar(tmp_path):
    exe = tmp_path / "kustom" / "DiscoveryStudio2024.exe"
    exe.parent.mkdir()
    exe.write_text("x")
    locator = _locator([], registry={f"{APP_PATHS}\\DiscoveryStudio2024.exe": {"": str(exe)}},
                       keys=["DiscoveryStudio2024.exe", "notepad.exe"])
    assert locator.find_executable() == exe


def test_registry_ke_berkas_yang_hilang_diabaikan(tmp_path):
    locator = _locator([], registry={f"{APP_PATHS}\\DiscoveryStudio2024.exe": {"": str(tmp_path / "hilang.exe")}},
                       keys=["DiscoveryStudio2024.exe"])
    assert locator.find_executable() is None


def test_jalur_eksplisit_berupa_berkas_folder_bin_atau_folder_instalasi(tmp_path):
    folder = _install(tmp_path, 2021)
    locator = _locator([])
    exe = folder / "bin" / "DiscoveryStudio2021.exe"
    assert locator.find_executable(exe) == exe
    assert locator.find_executable(folder / "bin") == exe
    assert locator.find_executable(folder) == exe


def test_jalur_eksplisit_salah_raise(tmp_path):
    with pytest.raises(FileNotFoundError, match="tidak ditemukan"):
        _locator([]).find_executable(tmp_path / "tidak_ada.exe")


def test_app_paths_dari_registry_menjadi_awal_path(tmp_path):
    exe = tmp_path / "bin" / "DiscoveryStudio2021.exe"
    extra = os.pathsep.join([str(tmp_path / "bin"), str(tmp_path / "LicensePack")])
    locator = _locator([], registry={f"{APP_PATHS}\\DiscoveryStudio2021.exe": {"Path": extra}})
    assert [str(p) for p in locator.app_paths(exe)] == [str(tmp_path / "bin"), str(tmp_path / "LicensePack")]

    env = locator.launch_environment(exe)
    assert env["PATH"].startswith(extra + os.pathsep)
    assert env["PATH"].endswith(os.environ.get("PATH", ""))


def test_app_paths_tanpa_registry_memakai_folder_exe_dan_licensepack(tmp_path, monkeypatch):
    shared = tmp_path / "Common" / "BIOVIA" / "LicensePack"
    shared.mkdir(parents=True)
    monkeypatch.setenv("CommonProgramFiles(x86)", str(tmp_path / "Common"))
    exe = tmp_path / "bin" / "DiscoveryStudio2021.exe"
    assert _locator([]).app_paths(exe) == [exe.parent, shared]


def test_launch_membawa_environment_dan_direktori_kerja(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "DiscoveryStudio2021.exe"
    locator = _locator([], registry={f"{APP_PATHS}\\DiscoveryStudio2021.exe": {"Path": str(tmp_path / "bin")}})
    captured = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured.update(args=args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    locator.launch(exe)
    assert captured["args"] == [str(exe)]
    assert captured["cwd"] == str(exe.parent)
    assert captured["env"]["PATH"].startswith(str(tmp_path / "bin"))
    assert captured["stdin"] == subprocess.DEVNULL
