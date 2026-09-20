"""Test pembaca data GC-MS: satuan RT, format sectioned Shimadzu, tabel generik, netCDF, mzML, mzXML."""

import numpy as np
import pandas as pd
import pytest

from chemflow.gcms.readers import (
    GcmsFormatError, collect_files, normalize_rt, read_data, read_file,
)
from tests.gcms_data import (
    make_trace, synthetic_peaks, write_cdf, write_mzml, write_mzxml, write_shimadzu_text,
    write_two_column_csv,
)


@pytest.fixture
def trace():
    return make_trace(synthetic_peaks(), rt_start=5.0, rt_end=15.0, step=0.01, seed=3)


# ------------------------------------------------------------------ satuan RT

def test_rt_menit_dibiarkan():
    rt = np.arange(5.0, 45.0, 0.005)
    scaled, factor = normalize_rt(rt)
    assert factor == 1.0 and scaled[0] == 5.0


def test_rt_menit_terkali_1000_diperbaiki_lewat_event_time():
    rt = np.arange(5000.0, 44000.0, 5.0)
    scaled, factor = normalize_rt(rt, event_msec=300.0)
    assert factor == pytest.approx(1 / 1000) and scaled[0] == pytest.approx(5.0) and scaled[-1] == pytest.approx(43.995)


def test_rt_menit_terkali_1000_diperbaiki_tanpa_event_time():
    _, factor = normalize_rt(np.arange(5000.0, 44000.0, 5.0))
    assert factor == pytest.approx(1 / 1000)


def test_rt_detik_dikenali_dari_selang_titik():
    scaled, factor = normalize_rt(np.arange(300.0, 2400.0, 0.3))
    assert factor == pytest.approx(1 / 60) and scaled[0] == pytest.approx(5.0)


def test_rt_daftar_puncak_pendek_dibiarkan_dan_besar_dianggap_detik():
    assert normalize_rt([6.1, 9.4, 12.8])[1] == 1.0
    assert normalize_rt([366.0, 564.0, 768.0])[1] == pytest.approx(1 / 60)


def test_petunjuk_satuan_dari_judul_kolom_didahulukan():
    assert normalize_rt([90.0, 120.0, 150.0], hint="sec")[1] == pytest.approx(1 / 60)


def test_satuan_dipaksa_menimpa_deteksi():
    scaled, factor = normalize_rt(np.arange(5.0, 45.0, 0.005), unit="sec")
    assert factor == pytest.approx(1 / 60) and scaled[0] == pytest.approx(5 / 60)


def test_satuan_tidak_dikenal_ditolak():
    with pytest.raises(ValueError, match="Satuan RT"):
        normalize_rt([1.0, 2.0], unit="jam")


# ------------------------------------------------------------------ Shimadzu

def test_shimadzu_teks_dengan_rt_terkali_1000(tmp_path, trace):
    path = write_shimadzu_text(tmp_path / "AQUATIC 2.txt", *trace, rt_factor=1000.0)
    (chrom,), table = read_file(path)
    assert table is None
    assert chrom.name == "AQUATIC 2" and chrom.meta["signal_label"] == "1-1 TIC"
    assert chrom.rt[0] == pytest.approx(5.0) and chrom.rt[-1] == pytest.approx(trace[0][-1])
    assert chrom.scan_interval == pytest.approx(0.01)
    assert chrom.intensity.max() == pytest.approx(trace[1].max(), rel=1e-4)


def test_shimadzu_tabel_puncak_membawa_nama(tmp_path, trace):
    peaks = [(9.5, 1.0e5, 1.2e6, "Linalool"), (15.2, 5.0e4, 7.0e5, "Coumarin")]
    path = write_shimadzu_text(tmp_path / "s.txt", *trace, peaks=peaks)
    (chrom,), _ = read_file(path)
    assert [p.name for p in chrom.peaks] == ["Linalool", "Coumarin"]
    assert chrom.peaks[0].rt == pytest.approx(9.5) and chrom.peaks[0].area == pytest.approx(1.0e5)
    assert chrom.peaks[0].start == pytest.approx(9.45) and chrom.peaks[0].end == pytest.approx(9.55)


def test_shimadzu_excel_sama_dengan_teks(tmp_path, trace):
    rows = [["[Header]", None], ["Data File Name", "x.qgd"], [None], ["[MS Chromatogram]", None], ["m/z", "1-1 TIC"],
            ["Event Time(msec)", 600.0], ["Ret.Time", "Absolute Intensity", "Relative Intensity"]]
    rows += [[r * 1000.0, float(v), "1.0"] for r, v in zip(*trace)]
    width = max(len(r) for r in rows)
    frame = pd.DataFrame([r + [None] * (width - len(r)) for r in rows])
    path = tmp_path / "AQUATIC 2.xlsx"
    frame.to_excel(path, header=False, index=False)
    (chrom,), _ = read_file(path)
    assert chrom.name == "AQUATIC 2" and chrom.rt[0] == pytest.approx(5.0) and chrom.scan_interval == pytest.approx(0.01)


def test_shimadzu_utf16_dan_titik_koma_terbaca(tmp_path, trace):
    path = tmp_path / "u16.txt"
    text = write_shimadzu_text(tmp_path / "tmp.txt", *trace).read_text(encoding="utf-8")
    path.write_bytes(text.encode("utf-16"))
    (chrom,), _ = read_file(path)
    assert chrom.has_signal and chrom.rt[0] == pytest.approx(5.0)


# ------------------------------------------------------------------ tabel generik

def test_csv_dua_kolom_berjudul(tmp_path, trace):
    (chrom,), _ = read_file(write_two_column_csv(tmp_path / "a.csv", *trace))
    assert chrom.name == "a" and chrom.rt.size == trace[0].size


def test_csv_tanpa_judul_dua_kolom_angka(tmp_path, trace):
    (chrom,), _ = read_file(write_two_column_csv(tmp_path / "b.csv", *trace, header=None))
    assert chrom.has_signal and chrom.scan_interval == pytest.approx(0.01)


def test_csv_titik_koma_dengan_koma_desimal(tmp_path, trace):
    path = write_two_column_csv(tmp_path / "c.csv", *trace, header=("RT", "Signal"), delimiter=";", decimal=",")
    (chrom,), _ = read_file(path)
    assert chrom.rt[0] == pytest.approx(5.0) and chrom.intensity.max() == pytest.approx(trace[1].max(), rel=1e-3)


def test_satuan_detik_dari_judul_kolom(tmp_path, trace):
    rt, y = trace
    (chrom,), _ = read_file(write_two_column_csv(tmp_path / "d.csv", rt * 60.0, y, header=("Time (sec)", "Abundance")))
    assert chrom.rt[0] == pytest.approx(5.0)


def test_banyak_kromatogram_berdampingan_satu_kolom_per_sampel(tmp_path, trace):
    rt, y = trace
    frame = pd.DataFrame({"RT": rt, "Melati 1": y, "Mawar 1": y * 0.5})
    path = tmp_path / "wide.csv"
    frame.to_csv(path, index=False)
    chroms, _ = read_file(path)
    assert [c.name for c in chroms] == ["Melati 1", "Mawar 1"]
    assert chroms[1].intensity.max() == pytest.approx(chroms[0].intensity.max() / 2, rel=1e-3)


def test_tabel_puncak_saja_tanpa_sinyal(tmp_path):
    path = tmp_path / "peaks.csv"
    pd.DataFrame({"RT": [6.1, 9.4, 12.8], "Area": [1e5, 3e5, 2e5], "Height": [1e4, 3e4, 2e4],
                  "Name": ["Limonene", "Linalool", "Citral"], "CAS": ["5989-27-5", "78-70-6", "5392-40-5"]}).to_csv(path, index=False)
    (chrom,), _ = read_file(path)
    assert not chrom.has_signal and len(chrom.peaks) == 3
    assert chrom.peaks[1].name == "Linalool" and chrom.peaks[1].cas == "78-70-6" and chrom.peaks[1].area == 3e5


def test_tabel_puncak_bahasa_indonesia(tmp_path):
    path = tmp_path / "puncak.csv"
    pd.DataFrame({"Waktu Retensi": [6.1, 9.4], "Luas": [1e5, 3e5], "Tinggi": [1e4, 3e4], "Nama": ["A", "B"]}).to_csv(path, index=False)
    (chrom,), _ = read_file(path)
    assert [p.name for p in chrom.peaks] == ["A", "B"] and chrom.peaks[0].height == 1e4


def test_matriks_fitur_sampel_di_baris(tmp_path):
    path = tmp_path / "fitur.csv"
    pd.DataFrame({"Sample": ["S1", "S2", "S3"], "Limonene": [1.0, 2.0, 3.0], "Linalool": [4.0, 5.0, 7.0]}).to_csv(path, index=False)
    chroms, table = read_file(path)
    assert chroms == [] and table.samples == ["S1", "S2", "S3"] and table.features == ["Limonene", "Linalool"]
    assert table.values.shape == (3, 2)


def test_matriks_fitur_ditranspos_bila_sudut_kiri_menyebut_fitur(tmp_path):
    path = tmp_path / "fitur_t.csv"
    pd.DataFrame({"Compound": ["Limonene", "Linalool", "Citral"], "S1": [1.0, 2.0, 3.0], "S2": [4.0, 5.0, 6.0]}).to_csv(path, index=False)
    _, table = read_file(path)
    assert table.samples == ["S1", "S2"] and table.features == ["Limonene", "Linalool", "Citral"]
    assert table.values[0].tolist() == [1.0, 2.0, 3.0]


def test_isi_tidak_dikenali_memberi_pesan_jelas(tmp_path):
    path = tmp_path / "aneh.csv"
    path.write_text("halo,dunia\nfoo,bar\n", encoding="utf-8")
    with pytest.raises(GcmsFormatError, match="kromatogram, tabel puncak"):
        read_file(path)


def test_ekstensi_tidak_didukung(tmp_path):
    path = tmp_path / "x.pdf"
    path.write_text("x")
    with pytest.raises(GcmsFormatError, match="tidak didukung"):
        read_file(path)


# ------------------------------------------------------------------ biner dan XML

def test_cdf_andi_ms(tmp_path, trace):
    (chrom,), _ = read_file(write_cdf(tmp_path / "s.cdf", *trace))
    assert chrom.name == "s" and chrom.rt[0] == pytest.approx(5.0) and chrom.intensity.max() == pytest.approx(trace[1].max())
    assert chrom.meta["experiment_title"] == "synthetic"


def test_cdf_bukan_netcdf_klasik(tmp_path):
    path = tmp_path / "rusak.cdf"
    path.write_bytes(b"bukan netcdf sama sekali")
    with pytest.raises(GcmsFormatError, match="netCDF klasik"):
        read_file(path)


@pytest.mark.parametrize("compress", [True, False])
def test_mzml_tic_dari_spektrum(tmp_path, trace, compress):
    rt, y = trace[0][:300], trace[1][:300]
    (chrom,), _ = read_file(write_mzml(tmp_path / "s.mzML", rt, y, compress=compress))
    assert chrom.rt.size == 300 and chrom.rt[0] == pytest.approx(rt[0]) and chrom.intensity[10] == pytest.approx(y[10])


def test_mzml_kromatogram_tic_langsung(tmp_path, trace):
    rt, y = trace
    (chrom,), _ = read_file(write_mzml(tmp_path / "t.mzML", rt, y, tic_chromatogram=True))
    assert chrom.rt.size == rt.size and chrom.intensity.max() == pytest.approx(y.max())


@pytest.mark.parametrize("attribute", [True, False])
def test_mzxml_tic_dari_atribut_atau_puncak(tmp_path, trace, attribute):
    rt, y = trace[0][:200], np.abs(trace[1][:200])
    (chrom,), _ = read_file(write_mzxml(tmp_path / "s.mzXML", rt, y, with_tic_attribute=attribute))
    assert chrom.rt.size == 200 and chrom.rt[5] == pytest.approx(rt[5], abs=1e-3)
    assert chrom.intensity[7] == pytest.approx(y[7], rel=1e-4)


# ------------------------------------------------------------------ pengumpulan berkas

def test_folder_rekursif_memberi_label_subfolder(tmp_path, trace):
    for folder in ("Asli", "Tiruan"):
        (tmp_path / folder).mkdir()
        write_two_column_csv(tmp_path / folder / f"{folder}_1.csv", *trace)
    found = collect_files([tmp_path])
    assert {label for _, label in found} == {"Asli", "Tiruan"}


def test_pola_glob_dan_pengecualian_folder_keluaran(tmp_path, trace):
    write_two_column_csv(tmp_path / "a.csv", *trace)
    (tmp_path / "gcms").mkdir()
    write_two_column_csv(tmp_path / "gcms" / "hasil.csv", *trace)
    assert len(collect_files([str(tmp_path / "*.csv")])) == 1
    assert [f.name for f, _ in collect_files([tmp_path], exclude_dirs=[tmp_path / "gcms"])] == ["a.csv"]


def test_berkas_hilang_memberi_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="tidak ditemukan"):
        collect_files([tmp_path / "tidak-ada.csv"])


def test_read_data_melewati_berkas_rusak_dan_menamai_ulang_duplikat(tmp_path, trace, caplog):
    for folder in ("x", "y"):
        (tmp_path / folder).mkdir()
        write_two_column_csv(tmp_path / folder / "sama.csv", *trace)
    (tmp_path / "rusak.csv").write_text("halo,dunia\nfoo,bar\n", encoding="utf-8")
    dataset = read_data([tmp_path])
    names = sorted(c.name for c in dataset.chromatograms)
    assert len(names) == 2 and len(set(names)) == 2
    assert [p.name for p, _ in dataset.skipped] == ["rusak.csv"]


def test_read_data_tanpa_berkas_yang_didukung(tmp_path):
    (tmp_path / "catatan.md").write_text("x")
    with pytest.raises(FileNotFoundError, match="Tidak ada berkas GC-MS"):
        read_data([tmp_path])
