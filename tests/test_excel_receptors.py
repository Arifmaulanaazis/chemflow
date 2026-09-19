"""Test pembaca Excel reseptor: kolom wajib, gridbox opsional, multi-situs."""

import pandas as pd
import pytest

from chemflow.io.excel_receptors import read_receptors


def test_kolom_pdb_wajib_terdeteksi(tmp_path):
    df = pd.DataFrame({"pdb_code": ["6LU7", "1AKI"]})
    path = tmp_path / "reseptor.xlsx"
    df.to_excel(path, index=False)

    entries = read_receptors(path)
    assert len(entries) == 2
    assert entries[0].pdb_code == "6LU7"
    assert entries[0].has_gridbox_center is False


def test_gridbox_lengkap_terdeteksi(tmp_path):
    df = pd.DataFrame({
        "pdb_code": ["6LU7"], "center_x": [10.5], "center_y": [20.1], "center_z": [-5.3],
        "size_x": [20], "size_y": [20], "size_z": [20],
    })
    path = tmp_path / "reseptor.xlsx"
    df.to_excel(path, index=False)

    entries = read_receptors(path)
    assert entries[0].has_gridbox_center is True
    assert entries[0].center_x == 10.5
    assert entries[0].size_x == 20.0


def test_multi_situs_kode_duplikat_dipertahankan(tmp_path):
    df = pd.DataFrame({
        "pdb_code": ["6LU7", "6LU7"],
        "center_x": [1.0, 5.0], "center_y": [1.0, 5.0], "center_z": [1.0, 5.0],
    })
    path = tmp_path / "reseptor.xlsx"
    df.to_excel(path, index=False)

    entries = read_receptors(path)
    assert len(entries) == 2
    assert entries[0].unique_key != entries[1].unique_key  # kunci unik beda meski kode sama


def test_tanpa_kolom_pdb_raise(tmp_path):
    df = pd.DataFrame({"foo": ["bar"]})
    path = tmp_path / "reseptor.xlsx"
    df.to_excel(path, index=False)
    with pytest.raises(ValueError):
        read_receptors(path)


def test_file_tidak_ditemukan():
    with pytest.raises(FileNotFoundError):
        read_receptors("tidak_ada.xlsx")
