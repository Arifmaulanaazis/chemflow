"""Test pembaca file hasil ADMETLab3 (CSV/Excel) dan pemetaan posisional ke ligan."""

import logging

import pandas as pd
import pytest

from chemflow.admet.admet_file import load_admet_rows, read_admet_table


def _table():
    return pd.DataFrame({
        "raw_smiles": ["CCO", "CCC", "CCCC"],
        "smiles": ["CCO", "CCC", "CCCC"],
        "MW": [46.07, 44.1, 58.1],
        "hERG": [0.1, 0.5, 0.9],
        "PAINS": ["['-']", "['-']", "[(1, 2)]"],
    })


def test_baca_csv(tmp_path):
    path = tmp_path / "admet.csv"
    _table().to_csv(path, index=False)
    df = read_admet_table(path)
    assert len(df) == 3
    assert "hERG" in df.columns


def test_baca_xlsx(tmp_path):
    path = tmp_path / "admet.xlsx"
    _table().to_excel(path, sheet_name="ADMETLab3", index=False)
    assert len(read_admet_table(path)) == 3


def test_file_tidak_ada_raise(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_admet_table(tmp_path / "tidak_ada.csv")


def test_ekstensi_tak_didukung_raise(tmp_path):
    path = tmp_path / "admet.txt"
    path.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="tidak didukung"):
        read_admet_table(path)


def test_file_kosong_raise(tmp_path):
    path = tmp_path / "kosong.csv"
    pd.DataFrame(columns=["MW", "hERG"]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="tidak berisi baris"):
        read_admet_table(path)


def test_pemetaan_posisional_sesuai_urutan_ligan(tmp_path):
    path = tmp_path / "admet.csv"
    _table().to_csv(path, index=False)

    rows = load_admet_rows(path, ["Etanol", "Propana", "Butana"])
    assert [r["ligand"] for r in rows] == ["Etanol", "Propana", "Butana"]
    assert rows[0]["hERG"] == pytest.approx(0.1)
    assert rows[2]["hERG"] == pytest.approx(0.9)
    assert rows[2]["PAINS"] == "[(1, 2)]"


def test_jumlah_baris_berbeda_raise_dengan_aturan_urutan(tmp_path):
    path = tmp_path / "admet.csv"
    _table().to_csv(path, index=False)
    with pytest.raises(ValueError, match="kolom kiri ke kanan"):
        load_admet_rows(path, ["A", "B"])


def test_nilai_kosong_menjadi_none(tmp_path):
    table = _table()
    table.loc[1, "hERG"] = None
    path = tmp_path / "admet.csv"
    table.to_csv(path, index=False)
    rows = load_admet_rows(path, ["A", "B", "C"])
    assert rows[1]["hERG"] is None


def test_smiles_tidak_cocok_hanya_warning(tmp_path, caplog):
    path = tmp_path / "admet.csv"
    _table().to_csv(path, index=False)
    with caplog.at_level(logging.WARNING):
        rows = load_admet_rows(path, ["A", "B", "C"], ["CCO", "CCCCC", "CCCC"])
    assert len(rows) == 3
    assert "tidak cocok" in caplog.text


def test_smiles_cocok_beda_penulisan_tanpa_warning(tmp_path, caplog):
    path = tmp_path / "admet.csv"
    _table().to_csv(path, index=False)
    with caplog.at_level(logging.WARNING):
        load_admet_rows(path, ["A", "B", "C"], ["OCC", "CCC", "CCCC"])
    assert "tidak cocok" not in caplog.text
