"""Test pembaca Excel ligan: mode tidy, wide, dan auto-detect."""

import pandas as pd
import pytest

from chemflow.io.excel_ligands import read_ligands


def test_mode_tidy_dengan_smiles_dan_group(tmp_path):
    df = pd.DataFrame({
        "name": ["Quercetin", "Curcumin"],
        "smiles": ["Oc1cc(O)c2c(=O)c(O)c(-c3ccc(O)c(O)c3)oc2c1", "COc1cc(C=CC(=O)CC(=O)C=Cc2ccc(O)c(OC)c2)ccc1O"],
        "group": ["Tanaman_X", "Tanaman_Y"],
    })
    path = tmp_path / "ligan.xlsx"
    df.to_excel(path, index=False)

    records = read_ligands(path)
    assert len(records) == 2
    assert records[0].name == "Quercetin"
    assert records[0].group == "Tanaman_X"
    assert records[0].needs_pubchem_lookup is False


def test_mode_tidy_smiles_kosong_perlu_pubchem(tmp_path):
    df = pd.DataFrame({"name": ["Aspirin", "Ibuprofen"], "smiles": ["", None]})
    path = tmp_path / "ligan.xlsx"
    df.to_excel(path, index=False)

    records = read_ligands(path)
    assert len(records) == 2
    assert all(r.needs_pubchem_lookup for r in records)


def test_mode_wide_multi_kolom_grup(tmp_path):
    df = pd.DataFrame({
        "Tanaman_X": ["Quercetin", "Kaempferol", "Rutin"],
        "Tanaman_Y": ["Curcumin", "Demethoxycurcumin", None],
    })
    path = tmp_path / "ligan.xlsx"
    df.to_excel(path, index=False)

    records = read_ligands(path)
    names_x = [r.name for r in records if r.group == "Tanaman_X"]
    names_y = [r.name for r in records if r.group == "Tanaman_Y"]
    assert names_x == ["Quercetin", "Kaempferol", "Rutin"]
    assert names_y == ["Curcumin", "Demethoxycurcumin"]  # baris None diabaikan
    assert all(r.needs_pubchem_lookup for r in records)


def test_file_tidak_ditemukan():
    with pytest.raises(FileNotFoundError):
        read_ligands("tidak_ada_file_ini.xlsx")


def test_tidy_tanpa_kolom_nama_raise(tmp_path):
    df = pd.DataFrame({"smiles": ["CCO"], "foo": ["bar"]})
    path = tmp_path / "ligan.xlsx"
    df.to_excel(path, index=False)
    with pytest.raises(ValueError):
        read_ligands(path)
