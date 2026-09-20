"""Test analisis GC-MS end-to-end pada studi sintetis: 2 kelas x 2 seri x 3 ulangan."""

import json
import logging

import numpy as np
import pandas as pd
import pytest

from chemflow import cli
from chemflow.gcms import (
    GcmsConfig, GcmsFormatError, assign_metadata, load_saved_config, read_groups_table, run_gcms_analysis,
)
from tests.gcms_data import build_study, make_trace, synthetic_peaks, write_shimadzu_text, write_two_column_csv

LOG = logging.getLogger("test-gcms")


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    root = tmp_path_factory.mktemp("studi")
    build_study(root / "data")
    library = pd.DataFrame({"name": ["Limonene", "Linalool", "Coumarin", "Senyawa Uji"], "rt": [8.0, 9.5, 15.2, 12.0],
                            "cas": ["5989-27-5", "78-70-6", "91-64-5", ""],
                            "smiles": ["CC1=CCC(CC1)C(C)=C", "CC(C)=CCCC(C)(O)C=C", "O=c1ccc2ccccc2o1", "CCO"]})
    library.to_csv(root / "library.csv", index=False)
    return root


@pytest.fixture(scope="module")
def outcome(study):
    cfg = GcmsConfig(data=[study / "data"], output_dir=study / "hasil", library=study / "library.csv",
                     n_permutations=40, dpi=80)
    return cfg, run_gcms_analysis(cfg, LOG)


def test_sampel_dan_metadata_diturunkan_dari_folder_dan_nama(outcome):
    _, result = outcome
    samples = result.samples
    assert len(samples) == 12
    assert set(samples["class"]) == {"Asli", "Tiruan"} and set(samples["series"]) == {"Melati", "Mawar"}
    assert (samples["jumlah_puncak"] >= 10).all() and (samples["jumlah_puncak"] <= 13).all()


def test_fitur_selaras_dan_penanda_kelas_terdeteksi(outcome):
    _, result = outcome
    features = result.features
    near = features[(features["rt_min"] - 16.0).abs() < 0.05]
    assert len(near) == 1
    columns = [c for c in features.columns if c.endswith("[total]")]
    assert len(columns) == 12
    values = near.iloc[0][columns].astype(float)
    tiruan = values[[c for c in columns if "(Tiruan)" in c]]
    asli = values[[c for c in columns if "(Asli)" in c]]
    assert len(tiruan) == len(asli) == 6
    assert tiruan.min() > 5 * max(asli.max(), 1e-9)


def test_univariat_menempatkan_penanda_teratas(outcome):
    _, result = outcome
    table = result.tables["univariat"]
    top = table.iloc[0]
    assert abs(top["rt_min"] - 12.0) < 0.05 or abs(top["rt_min"] - 16.0) < 0.05
    assert top["q_welch"] < 0.001
    marker16 = table[(table["rt_min"] - 16.0).abs() < 0.05].iloc[0]
    assert marker16["log2_fold_change"] > 3


def test_model_terawasi_memisahkan_asli_dan_tiruan(outcome):
    _, result = outcome
    klas = result.tables["klasifikasi"].set_index("metode")
    assert klas.loc["PLS-DA", "akurasi_CV_persen"] >= 90.0 and klas.loc["LDA", "akurasi_CV_persen"] >= 90.0
    assert klas.loc["PLS-DA", "p_permutasi"] < 0.1
    vip = result.tables["vip"]
    assert vip.iloc[0]["vip"] > 1.5 and (abs(vip.iloc[0]["rt_min"] - 12.0) < 0.05 or abs(vip.iloc[0]["rt_min"] - 16.0) < 0.05)


def test_pca_memakai_kelas_sebagai_penanda_dan_seri_sebagai_warna(outcome):
    _, result = outcome
    scores = result.tables["pca_scores"]
    assert list(scores.columns[:3]) == ["sample", "series", "class"] and "PC3" in scores.columns
    variance = result.tables["pca_variance"]
    assert variance["variance_percent"].sum() <= 100.0001 and variance["variance_percent"].iloc[0] > 30
    pc1 = scores.groupby("class")["PC1"].mean()
    assert abs(pc1["Asli"] - pc1["Tiruan"]) > 2


def test_nama_dari_pustaka_alergen_dan_ligan_untuk_docking(outcome):
    _, result = outcome
    named = result.features[result.features["nama"] != ""]
    assert set(named["nama"]) == {"Limonene", "Linalool", "Coumarin", "Senyawa Uji"}
    allergens = result.tables["alergen"]
    assert set(allergens["alergen"]) == {"Limonene", "Linalool", "Coumarin"}
    ligands = pd.read_excel(result.ligands_file)
    assert list(ligands.columns) == ["name", "smiles", "group"] and len(ligands) == 4
    assert set(ligands["group"]) <= {"Melati", "Mawar"}
    from chemflow.io.excel_ligands import read_ligands
    assert len(read_ligands(result.ligands_file)) == 4


def test_workbook_grafik_dan_konfigurasi_tersimpan(outcome):
    cfg, result = outcome
    sheets = set(pd.ExcelFile(result.workbook).sheet_names)
    assert {"Sampel", "Puncak", "Fitur Selaras", "Uji Univariat", "VIP PLS-DA", "Klasifikasi", "PCA Skor", "PCA Loading",
            "Kemiripan Kosinus", "Alergen", "Catatan", "Parameter"} <= sheets
    names = {p.name for p in result.plots}
    for expected in ("pca_2d.png", "pca_3d.png", "pca_variansi.png", "pca_loading_rt.png", "hca_dendrogram.png",
                     "kromatogram_tumpang_tindih.png", "penyelarasan_rt.png", "peta_panas_fitur.png", "vip.png",
                     "volcano.png", "plsda_skor.png", "konfusi_plsda.png", "permutasi_lda.png", "alergen.png",
                     "kemiripan_kosinus.png", "cermin_Asli_vs_Tiruan.png"):
        assert expected in names, expected
    assert all(p.stat().st_size > 0 for p in result.plots)
    saved = load_saved_config(cfg.output_dir)
    assert saved.data == cfg.data and saved.library == cfg.library and saved.n_permutations == 40


def test_analisis_hanya_menulis_di_subfolder_gcms(outcome):
    cfg, _ = outcome
    assert {p.name for p in cfg.output_dir.iterdir()} == {"gcms"}


def test_penyelarasan_menjaga_jumlah_fitur_tetap_wajar(outcome):
    _, result = outcome
    assert 10 <= len(result.features) <= 30


def test_satu_sampel_tetap_memproses_puncak_tanpa_perbandingan(tmp_path):
    write_two_column_csv(tmp_path / "tunggal.csv", *make_trace(synthetic_peaks()))
    result = run_gcms_analysis(GcmsConfig(data=[tmp_path / "tunggal.csv"], output_dir=tmp_path / "o", dpi=70), LOG)
    assert len(result.samples) == 1 and result.samples["jumlah_puncak"].iloc[0] == 10
    assert result.workbook.exists() and "pca_2d.png" not in {p.name for p in result.plots}


def test_data_tanpa_kelas_memakai_seri_sebagai_kelompok_tanpa_terawasi(tmp_path):
    for name, scale in (("PARFUM A 1", 1.0), ("PARFUM B 1", 0.5), ("PARFUM C 1", 2.0), ("PARFUM D 1", 3.0)):
        rt, y = make_trace(synthetic_peaks({9.5: scale, 12.0: 4.0 - scale}), seed=hash(name) % 1000)
        write_two_column_csv(tmp_path / f"{name}.csv", rt, y)
    result = run_gcms_analysis(GcmsConfig(data=[tmp_path], output_dir=tmp_path / "out", dpi=70), LOG)
    assert set(result.samples["series"]) == {"PARFUM A", "PARFUM B", "PARFUM C", "PARFUM D"}
    assert set(result.samples["class"]) == {"Sampel"}
    assert "klasifikasi" not in result.tables and "univariat" not in result.tables
    assert any("dilewati" in n for n in result.notes)
    assert "pca_2d.png" in {p.name for p in result.plots}


def test_kromatogram_shimadzu_dengan_rt_terkali_1000_dianalisis_benar(tmp_path):
    for k in (1, 2):
        rt, y = make_trace(synthetic_peaks(), seed=k)
        write_shimadzu_text(tmp_path / f"SAMPEL {k}.txt", rt, y, rt_factor=1000.0)
    result = run_gcms_analysis(GcmsConfig(data=[tmp_path], output_dir=tmp_path / "out", dpi=70), LOG)
    assert result.features["rt_min"].min() > 5.0 and result.features["rt_min"].max() < 21.0


def test_tabel_puncak_instrumen_membawa_nama_ke_hasil(tmp_path):
    for k, scale in ((1, 1.0), (2, 1.2), (3, 0.8)):
        pd.DataFrame({"RT": [6.0, 8.0, 9.5, 15.2], "Area": [1e5 * scale, 2e5, 3e5 * scale, 2e5], "Height": [1e4] * 4,
                      "Name": ["Benzyl alcohol", "Limonene", "Linalool", "Unknown"]}).assign(
            Area=lambda d: d["Area"] * (1 + 0.02 * k)).to_csv(tmp_path / f"S{k}.csv", index=False)
    result = run_gcms_analysis(GcmsConfig(data=[tmp_path], output_dir=tmp_path / "out", dpi=70), LOG)
    assert {"Benzyl alcohol", "Limonene", "Linalool"} <= set(result.features["nama"])
    assert set(result.tables["alergen"]["alergen"]) == {"Benzyl alcohol", "Limonene", "Linalool"}
    assert "puncak" in result.tables


def test_tabel_fitur_langsung_diuji_tanpa_pemrosesan_sinyal(tmp_path):
    rng = np.random.default_rng(0)
    rows = []
    for k in range(8):
        cls = "Asli" if k < 4 else "Tiruan"
        rows.append({"Sample": f"{cls}_{k}", "Limonene": rng.normal(10, 1) + (5 if cls == "Tiruan" else 0),
                     "Linalool": rng.normal(20, 1), "Citral": rng.normal(5, 1), "Geraniol": rng.normal(7, 1)})
    pd.DataFrame(rows).to_csv(tmp_path / "fitur.csv", index=False)
    result = run_gcms_analysis(GcmsConfig(data=[tmp_path / "fitur.csv"], output_dir=tmp_path / "o", dpi=70,
                                          n_permutations=20), LOG)
    assert set(result.samples["class"]) == {"Asli", "Tiruan"}
    assert set(result.features["nama"]) == {"Limonene", "Linalool", "Citral", "Geraniol"}
    assert result.tables["univariat"].iloc[0]["feature"].startswith("Limonene")
    assert {"Limonene", "Linalool", "Citral", "Geraniol"} >= set(result.tables["alergen"]["alergen"])


def test_tabel_kelompok_menimpa_penurunan_otomatis(tmp_path):
    for name in ("x1", "x2", "y1", "y2"):
        write_two_column_csv(tmp_path / f"{name}.csv", *make_trace(synthetic_peaks(), seed=hash(name) % 100))
    groups = tmp_path / "grup.csv"
    pd.DataFrame({"sample": ["x1", "x2", "y1", "y2"], "series": ["S1", "S1", "S2", "S2"],
                  "class": ["Asli", "Asli", "Tiruan", "Tiruan"]}).to_csv(groups, index=False)
    table = read_groups_table(groups)
    meta = assign_metadata(["x1", "y2", "z9"], {}, table, LOG)
    assert [(m.series, m.group) for m in meta] == [("S1", "Asli"), ("S2", "Tiruan"), ("z", "Sampel")]


def test_folder_hanya_dipakai_sebagai_kelas_bila_ada_minimal_dua(tmp_path):
    only = assign_metadata(["a 1"], {"a 1": "SatuFolder"}, None, LOG)
    assert only[0].group == "Sampel"
    two = assign_metadata(["a 1", "b 1"], {"a 1": "F1", "b 1": "F2"}, None, LOG)
    assert [m.group for m in two] == ["F1", "F2"]
    kata = assign_metadata(["Melati Asli 1", "Melati Tiruan 1"], {}, None, LOG)
    assert [m.group for m in kata] == ["Asli", "Tiruan"]


def test_tabel_kelompok_tanpa_kolom_kelas_atau_seri_ditolak(tmp_path):
    path = tmp_path / "g.csv"
    pd.DataFrame({"sample": ["a"], "warna": ["merah"]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="seri"):
        read_groups_table(path)
    with pytest.raises(FileNotFoundError):
        read_groups_table(tmp_path / "tidak-ada.csv")


def test_konfigurasi_divalidasi(tmp_path):
    base = dict(data=[tmp_path], output_dir=tmp_path)
    for bad, pattern in ((dict(rt_unit="jam"), "rt_unit"), (dict(scaling="log"), "scaling"),
                         (dict(normalization="x"), "normalization"), (dict(feature_mode="x"), "feature_mode"),
                         (dict(min_presence=2.0), "min_presence"), (dict(bin_width=0.0), "bin_width"),
                         (dict(rt_range=(10.0, 5.0)), "rt_range"), (dict(min_snr=-1.0), "min_snr")):
        with pytest.raises(ValueError, match=pattern):
            GcmsConfig(**{**base, **bad})
    with pytest.raises(ValueError, match="kosong"):
        GcmsConfig(data=[], output_dir=tmp_path)


def test_konfigurasi_bolak_balik_dict_dan_json(tmp_path):
    cfg = GcmsConfig(data=[tmp_path / "a", tmp_path / "b"], output_dir=tmp_path, rt_range=(6.0, 20.0),
                     figure_formats=("png", "svg"), library=tmp_path / "lib.csv")
    again = GcmsConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
    assert again.data == cfg.data and again.rt_range == (6.0, 20.0) and again.figure_formats == ("png", "svg")
    assert again.library == cfg.library


def test_mode_sidik_jari_memakai_bin_waktu_sebagai_fitur(tmp_path):
    for k, scale in ((1, 1.0), (2, 1.1), (3, 6.0), (4, 5.5)):
        write_two_column_csv(tmp_path / f"{'A' if k < 3 else 'B'} {k}.csv",
                             *make_trace(synthetic_peaks({12.0: scale}), seed=k))
    result = run_gcms_analysis(GcmsConfig(data=[tmp_path], output_dir=tmp_path / "o", feature_mode="bins", bin_width=0.1,
                                          dpi=70, n_permutations=10, make_plots=False), LOG)
    assert len(result.features) == pytest.approx(160, abs=2)
    assert result.features["rt_min"].diff().dropna().round(3).eq(0.1).all()
    assert (result.features["nama"] == "").all()


def test_rt_range_membatasi_fitur(tmp_path):
    for k in (1, 2):
        write_two_column_csv(tmp_path / f"S{k}.csv", *make_trace(synthetic_peaks(), seed=k))
    result = run_gcms_analysis(GcmsConfig(data=[tmp_path], output_dir=tmp_path / "o", rt_range=(8.5, 14.0), dpi=70, make_plots=False), LOG)
    assert result.features["rt_min"].between(8.5, 14.0).all() and result.plots == []


def test_hanya_satu_kelompok_data_puncak_dan_sinyal_bercampur_ditolak(tmp_path):
    write_two_column_csv(tmp_path / "S1.csv", *make_trace(synthetic_peaks()))
    pd.DataFrame({"RT": [6.0], "Area": [1.0], "Height": [1.0]}).to_csv(tmp_path / "S2.csv", index=False)
    with pytest.raises(ValueError, match="hanya berisi tabel puncak"):
        run_gcms_analysis(GcmsConfig(data=[tmp_path], output_dir=tmp_path / "o", dpi=70), LOG)


def test_masukan_kosong_atau_rusak_gagal_jelas(tmp_path):
    (tmp_path / "kosong").mkdir()
    with pytest.raises(FileNotFoundError, match="Tidak ada berkas GC-MS"):
        run_gcms_analysis(GcmsConfig(data=[tmp_path / "kosong"], output_dir=tmp_path / "o"), LOG)
    (tmp_path / "rusak.csv").write_text("halo,dunia\nx,y\n")
    with pytest.raises(GcmsFormatError):
        run_gcms_analysis(GcmsConfig(data=[tmp_path / "rusak.csv"], output_dir=tmp_path / "o"), LOG)


# ------------------------------------------------------------------ CLI

def test_parser_gcms_bawaan_dan_opsi():
    args = cli.build_parser().parse_args(["gcms", "--output", "h"])
    assert args.command == "gcms" and args.data is None and cli._gcms_overrides(args) == {}
    args = cli.build_parser().parse_args(["gcms", "--output", "h", "--data", "a", "b", "--rt-range", "6", "20", "--no-align",
                                          "--scaling", "auto", "--permutations", "0", "--no-plots", "--figure-formats", "png", "svg"])
    assert [str(p) for p in args.data] == ["a", "b"]
    overrides = cli._gcms_overrides(args)
    assert overrides["rt_range"] == (6.0, 20.0) and overrides["align"] is False and overrides["make_plots"] is False
    assert overrides["scaling"] == "auto" and overrides["n_permutations"] == 0 and overrides["figure_formats"] == ("png", "svg")
    args = cli.build_parser().parse_args(["gcms", "--output", "h", "--feature-mode", "bins", "--bin-width", "0.1"])
    assert cli._gcms_overrides(args) == {"feature_mode": "bins", "bin_width": 0.1}


def test_cli_gcms_mandiri_lalu_rerun_dari_konfigurasi_tersimpan(study, tmp_path, capsys):
    out = tmp_path / "keluaran"
    code = cli.main(["gcms", "--data", str(study / "data"), "--output", str(out), "--permutations", "10", "--dpi", "70",
                     "--library", str(study / "library.csv")])
    text = capsys.readouterr().out
    assert code == 0 and "12 sampel" in text and "Daftar senyawa untuk docking" in text
    assert (out / "gcms" / "analisis_gcms.xlsx").exists()
    first = (out / "gcms" / "analisis_gcms.xlsx").stat().st_mtime_ns
    code = cli.main(["gcms", "--output", str(out), "--no-plots"])
    assert code == 0 and (out / "gcms" / "analisis_gcms.xlsx").stat().st_mtime_ns >= first
    saved = load_saved_config(out)
    assert saved.n_permutations == 10 and saved.library is not None and saved.make_plots is False


def test_cli_gcms_tanpa_data_dan_tanpa_riwayat_gagal_jelas(tmp_path, capsys):
    assert cli.main(["gcms", "--output", str(tmp_path / "baru")]) == 1
    assert "tidak ada data GC-MS" in capsys.readouterr().out
    assert cli.main(["gcms", "--output", str(tmp_path), "--data", str(tmp_path / "hilang")]) == 1
    assert "Gagal" in capsys.readouterr().out
