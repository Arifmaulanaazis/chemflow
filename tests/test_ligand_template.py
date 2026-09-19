"""Test SMILES ligan native dengan orde ikatan dari templat RCSB (HTTP di-mock)."""

import logging

import pytest
import requests

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem
from rdkit.Chem import AllChem

from chemflow.io import ligand_template
from chemflow.io.ligand_template import assign_bond_orders, fetch_component_smiles, native_smiles

_BENZAMIDINE = "NC(=N)c1ccccc1"


def _crystal_block(smiles):
    """Blok PDB heavy-atom tanpa orde ikatan, seperti koordinat kristal ligan."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    mol = Chem.RemoveHs(mol)
    lines = [ln for ln in Chem.MolToPDBBlock(mol).splitlines() if ln.startswith(("ATOM", "HETATM"))]
    return "\n".join(line.replace("ATOM  ", "HETATM", 1) for line in lines) + "\nEND\n"


class _Response:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise requests.exceptions.HTTPError("404")

    def json(self):
        return self._payload


def _patch_get(monkeypatch, payload=None, exc=None, calls=None):
    def fake_get(url, timeout=None):
        if calls is not None:
            calls.append(url)
        if exc is not None:
            raise exc
        return _Response(payload)
    monkeypatch.setattr(ligand_template.requests, "get", fake_get)


def _canonical(smiles):
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


def test_assign_bond_orders_memulihkan_aromatisitas():
    fixed = assign_bond_orders(_crystal_block(_BENZAMIDINE), _BENZAMIDINE)
    assert fixed is not None
    assert Chem.MolToSmiles(fixed) == _canonical(_BENZAMIDINE)


def test_assign_bond_orders_templat_tak_cocok_return_none():
    assert assign_bond_orders(_crystal_block(_BENZAMIDINE), "CCCCCCCC") is None


def test_native_smiles_memakai_templat_rcsb(monkeypatch, tmp_path):
    _patch_get(monkeypatch, {"rcsb_chem_comp_descriptor": {"SMILES": _BENZAMIDINE}})
    result = native_smiles(_crystal_block(_BENZAMIDINE), "BEN", cache_dir=tmp_path)
    assert result == _canonical(_BENZAMIDINE)


def test_native_smiles_cadangan_saat_jaringan_gagal(monkeypatch, tmp_path, caplog):
    _patch_get(monkeypatch, exc=requests.exceptions.ConnectionError("offline"))
    with caplog.at_level(logging.WARNING):
        result = native_smiles(_crystal_block(_BENZAMIDINE), "BEN", cache_dir=tmp_path)
    assert Chem.MolFromSmiles(result) is not None
    assert result != _canonical(_BENZAMIDINE)  # jenuh, tanpa templat
    assert "tidak bisa diambil" in caplog.text


def test_native_smiles_cadangan_saat_templat_tidak_cocok(monkeypatch, tmp_path, caplog):
    _patch_get(monkeypatch, {"rcsb_chem_comp_descriptor": {"SMILES": "CCCCCCCC"}})
    with caplog.at_level(logging.WARNING):
        result = native_smiles(_crystal_block(_BENZAMIDINE), "BEN", cache_dir=tmp_path)
    assert result != "CCCCCCCC"
    assert "tidak cocok" in caplog.text


def test_fetch_component_smiles_disimpan_di_cache(monkeypatch, tmp_path):
    calls = []
    _patch_get(monkeypatch, {"rcsb_chem_comp_descriptor": {"SMILES_stereo": _BENZAMIDINE}}, calls=calls)

    assert fetch_component_smiles("ben", cache_dir=tmp_path) == _BENZAMIDINE
    assert fetch_component_smiles("BEN", cache_dir=tmp_path) == _BENZAMIDINE
    assert len(calls) == 1
    assert (tmp_path / "BEN.smi").exists()


def test_fetch_component_smiles_kode_kosong_return_none():
    assert fetch_component_smiles("  ") is None


def test_native_smiles_blok_tak_terbaca_raise(monkeypatch, tmp_path):
    _patch_get(monkeypatch, exc=requests.exceptions.ConnectionError("offline"))
    with pytest.raises(ValueError, match="memparse"):
        native_smiles("bukan blok pdb", "BEN", cache_dir=tmp_path)


def test_assign_bond_orders_templat_dengan_hidrogen_eksplisit():
    fixed = assign_bond_orders(_crystal_block(_BENZAMIDINE), r"[H]/N=C(\c1ccccc1)/N")
    assert fixed is not None
    assert Chem.MolToSmiles(fixed) == _canonical(_BENZAMIDINE)
