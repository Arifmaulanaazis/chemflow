"""Test system_check: tiap fungsi cek harus tetap tidak-raise di kondisi gagal."""

from types import SimpleNamespace

import chemflow.system_check as sc


def test_check_python_packages_format():
    results = sc.check_python_packages()
    names = {r.name for r in results}
    assert "rdkit" in names
    assert all(isinstance(r.ok, bool) for r in results)


def test_check_openbabel_tidak_ditemukan(monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda name: None)
    result = sc.check_openbabel()
    assert result.ok is False
    assert "obabel" in result.hint or "openbabel" in result.hint.lower()


def test_check_openbabel_ditemukan(monkeypatch, tmp_path):
    fake_exe = tmp_path / "obabel"
    fake_exe.write_text("dummy")
    monkeypatch.setattr(sc.shutil, "which", lambda name: str(fake_exe))

    def fake_run(cmd, capture_output, text, timeout):
        return SimpleNamespace(stdout="3.1.1\n", stderr="")

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    result = sc.check_openbabel()
    assert result.ok is True
    assert "3.1.1" in result.detail


def test_check_vina_tidak_raise_saat_network_gagal(monkeypatch):
    from chemflow.docking import vina_manager as vm

    def fail_network(*a, **k):
        raise ConnectionError("simulasi gagal")

    monkeypatch.setattr(vm.requests, "get", fail_network)

    results = sc.check_vina()
    assert len(results) == 2
    assert all(isinstance(r.ok, bool) for r in results)
    assert results[1].ok is False  # GitHub Releases check harus melaporkan gagal, bukan raise


def test_check_network_tidak_raise_saat_semua_gagal(monkeypatch):
    def fail(*a, **k):
        raise ConnectionError("simulasi offline")

    monkeypatch.setattr("requests.head", fail)
    monkeypatch.setattr("requests.get", fail)

    results = sc.check_network()
    assert len(results) == len(sc._NETWORK_TARGETS)
    assert all(r.ok is False for r in results)


def test_format_report_tidak_error_kosong():
    report = sc.format_report([])
    assert "Pemeriksaan Kesiapan Mesin" in report


def test_format_report_menandai_kegagalan():
    results = [sc.CheckResult("X", "Y", False, "gagal total", hint="perbaiki begini")]
    report = sc.format_report(results)
    assert "!!" in report
    assert "perbaiki begini" in report
