"""Test PubChemResolver. pubchempy di-mock (tidak ada request jaringan nyata)."""

from types import SimpleNamespace

import pytest

from chemflow.chem import pubchem_client as pc


class _FakeCompound:
    def __init__(self, smiles):
        self.smiles = smiles


def test_resolve_sukses(monkeypatch):
    fake_pcp = SimpleNamespace(get_compounds=lambda name, by: [_FakeCompound("CC(=O)OC1=CC=CC=C1C(=O)O")])
    monkeypatch.setitem(__import__("sys").modules, "pubchempy", fake_pcp)

    resolver = pc.PubChemResolver()
    assert resolver.resolve("Aspirin") == "CC(=O)OC1=CC=CC=C1C(=O)O"


def test_resolve_tidak_ditemukan(monkeypatch):
    fake_pcp = SimpleNamespace(get_compounds=lambda name, by: [])
    monkeypatch.setitem(__import__("sys").modules, "pubchempy", fake_pcp)

    resolver = pc.PubChemResolver()
    assert resolver.resolve("SenyawaFiktif") is None


def test_resolve_dicache_tidak_query_dua_kali(monkeypatch):
    call_count = {"n": 0}

    def fake_get_compounds(name, by):
        call_count["n"] += 1
        return [_FakeCompound("CCO")]

    fake_pcp = SimpleNamespace(get_compounds=fake_get_compounds)
    monkeypatch.setitem(__import__("sys").modules, "pubchempy", fake_pcp)

    resolver = pc.PubChemResolver()
    resolver.resolve("Etanol")
    resolver.resolve("etanol")  # case-insensitive, harus kena cache yang sama
    assert call_count["n"] == 1


def test_resolve_retry_lalu_sukses(monkeypatch):
    attempts = {"n": 0}

    def flaky_get_compounds(name, by):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ConnectionError("simulasi gagal sementara")
        return [_FakeCompound("CCO")]

    fake_pcp = SimpleNamespace(get_compounds=flaky_get_compounds)
    monkeypatch.setitem(__import__("sys").modules, "pubchempy", fake_pcp)

    resolver = pc.PubChemResolver(max_retries=3, retry_backoff_sec=0.0)
    assert resolver.resolve("Etanol") == "CCO"
    assert attempts["n"] == 2


def test_resolve_semua_percobaan_gagal_return_none(monkeypatch):
    def always_fail(name, by):
        raise ConnectionError("gagal terus")

    fake_pcp = SimpleNamespace(get_compounds=always_fail)
    monkeypatch.setitem(__import__("sys").modules, "pubchempy", fake_pcp)

    resolver = pc.PubChemResolver(max_retries=2, retry_backoff_sec=0.0)
    assert resolver.resolve("SenyawaBermasalah") is None


def test_smiles_fallback_ke_isomeric_smiles_jika_smiles_tak_ada(monkeypatch):
    class _OldStyleCompound:
        isomeric_smiles = "CCO"

    fake_pcp = SimpleNamespace(get_compounds=lambda name, by: [_OldStyleCompound()])
    monkeypatch.setitem(__import__("sys").modules, "pubchempy", fake_pcp)

    resolver = pc.PubChemResolver()
    assert resolver.resolve("Etanol") == "CCO"


def test_prompt_manual_smiles_non_tty_raise(monkeypatch):
    monkeypatch.setattr(pc.sys.stdin, "isatty", lambda: False)
    with pytest.raises(RuntimeError):
        pc.prompt_manual_smiles("Senyawa Misterius")


def test_prompt_manual_smiles_input_valid_langsung_diterima(monkeypatch):
    monkeypatch.setattr(pc.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "CCO")
    assert pc.prompt_manual_smiles("Etanol") == "CCO"


def test_prompt_manual_smiles_skip_via_s(monkeypatch):
    monkeypatch.setattr(pc.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "s")
    assert pc.prompt_manual_smiles("Senyawa Misterius") is None


def test_prompt_manual_smiles_skip_via_kosong(monkeypatch):
    monkeypatch.setattr(pc.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert pc.prompt_manual_smiles("Senyawa Misterius") is None


def test_prompt_manual_smiles_ulang_prompt_jika_invalid(monkeypatch):
    monkeypatch.setattr(pc.sys.stdin, "isatty", lambda: True)
    responses = iter(["bukan-smiles-valid", "CCO"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))
    assert pc.prompt_manual_smiles("Etanol") == "CCO"
