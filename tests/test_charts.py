"""Test ChartBuilder: bar, radar gabungan, radar dan bar klasifikasi ADMET, serta pemotongan otomatis."""

from chemflow.analytics.charts import ChartBuilder

_ROWS = [
    {"ligand": "A", "affinity_best": -7.0, "MW": 180.0, "LogP": 2.0},
    {"ligand": "B", "affinity_best": -5.0, "MW": 250.0, "LogP": 3.5},
    {"ligand": "C", "affinity_best": -6.0, "MW": 300.0, "LogP": 1.0},
]

_ADMET = [
    {"ligand": "A", "hia": 0.1, "caco2": -4.5, "pgp_inh": 0.2, "hERG": 0.2, "DILI": 0.5, "Ames": 0.1, "PPB": 50.0},
    {"ligand": "B", "hia": 0.9, "caco2": -6.0, "pgp_inh": 0.8, "hERG": 0.8, "DILI": 0.1, "Ames": 0.4, "PPB": 95.0},
    {"ligand": "C", "hia": 0.4, "caco2": -5.0, "pgp_inh": 0.5, "hERG": 0.3, "DILI": 0.9, "Ames": 0.9, "PPB": 70.0},
]


def _many(n):
    return [{"ligand": f"L{i:02d}", "affinity_best": -1.0 - 0.1 * i} for i in range(n)]


def test_bar_affinity_menghasilkan_file(tmp_path):
    paths = ChartBuilder(tmp_path).bar_affinity(_ROWS)
    assert [p.name for p in paths] == ["bar_affinity.png"]
    assert paths[0].exists() and paths[0].stat().st_size > 0


def test_bar_affinity_top_n(tmp_path):
    rows = [{"ligand": f"L{i}", "affinity_best": -float(i)} for i in range(1, 11)]
    paths = ChartBuilder(tmp_path).bar_affinity(rows, top_n=3, filename="top3.png")
    assert [p.name for p in paths] == ["top3.png"] and paths[0].exists()


def test_bar_affinity_nilai_positif_dan_negatif(tmp_path):
    rows = [{"ligand": "A", "affinity_best": -7.0}, {"ligand": "B", "affinity_best": 1.5}]
    assert ChartBuilder(tmp_path).bar_affinity(rows)[0].exists()


def test_bar_affinity_kosong_return_list_kosong(tmp_path):
    assert ChartBuilder(tmp_path).bar_affinity([]) == []


def test_format_tambahan_svg_pdf_ditulis_berdampingan(tmp_path):
    path = ChartBuilder(tmp_path, formats=("png", "svg", "pdf")).bar_affinity(_ROWS)[0]
    assert path.with_suffix(".svg").exists()
    assert path.with_suffix(".pdf").exists()


def test_bar_affinity_dipotong_seimbang_dan_bernama_bagian(tmp_path):
    paths = ChartBuilder(tmp_path, max_rows=4).bar_affinity(_many(10))
    assert [p.name for p in paths] == ["bar_affinity_part01of03.png", "bar_affinity_part02of03.png",
                                       "bar_affinity_part03of03.png"]
    assert all(p.exists() for p in paths)


def test_bar_affinity_tanpa_batas_tidak_dipotong(tmp_path):
    paths = ChartBuilder(tmp_path, max_rows=0).bar_affinity(_many(50))
    assert [p.name for p in paths] == ["bar_affinity.png"]


def test_bar_affinity_sumbu_x_sama_antar_bagian(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    limits = []
    original = plt.Axes.set_xlim

    def spy(self, *args, **kwargs):
        limits.append(args)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(plt.Axes, "set_xlim", spy)
    ChartBuilder(tmp_path, max_rows=4).bar_affinity(_many(10))
    explicit = [args for args in limits if len(args) == 2]
    assert len(explicit) == 3 and len(set(explicit)) == 1


def test_bar_affinity_native_disorot(tmp_path):
    rows = _ROWS + [{"ligand": "NATIVE_X", "affinity_best": -9.0}]
    paths = ChartBuilder(tmp_path).bar_affinity(rows, highlight_keys={"NATIVE_X"})
    assert paths[0].exists()


def test_radar_combined_menghasilkan_file(tmp_path):
    paths = ChartBuilder(tmp_path).radar_combined(
        _ROWS, criteria=["affinity_best", "MW", "LogP"], lower_is_better=["affinity_best"],
        criteria_labels={"affinity_best": "ΔG docking"},
    )
    assert len(paths) == 1 and paths[0].exists()


def test_radar_combined_kriteria_absolut_tanpa_minmax(tmp_path):
    rows = [{**r, "Absorpsi": s} for r, s in zip(_ROWS, (1.0, 0.5, 0.0))]
    paths = ChartBuilder(tmp_path).radar_combined(
        rows, criteria=["affinity_best", "MW", "Absorpsi"], absolute=["Absorpsi"],
    )
    assert len(paths) == 1


def test_radar_combined_data_tidak_lengkap_return_kosong(tmp_path):
    rows = [{"ligand": "A", "affinity_best": -7.0}]
    assert ChartBuilder(tmp_path).radar_combined(rows, criteria=["affinity_best", "MW", "LogP"]) == []


def test_radar_combined_kurang_dari_3_kriteria_return_kosong(tmp_path):
    assert ChartBuilder(tmp_path).radar_combined(_ROWS, criteria=["affinity_best", "MW"]) == []


def _capture_radar(monkeypatch, builder):
    calls = []

    def fake_draw(values, series_labels, axis_labels, title, **kwargs):
        calls.append(dict(values=values, series=series_labels, axes=axis_labels, title=title, **kwargs))
        return builder._dir / f"x{len(calls)}.png"

    monkeypatch.setattr(builder, "_draw_radar", fake_draw)
    return calls


def test_radar_combined_peringkat_menurut_kriteria_dibagi_ke_bagian(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    builder.radar_combined(
        _ROWS, criteria=["affinity_best", "MW", "LogP"], lower_is_better=["affinity_best"],
        criteria_labels={"affinity_best": "ΔG docking"}, top_n=2, rank_by="affinity_best",
    )
    assert [c["series"] for c in calls] == [["A", "C"], ["B"]]
    assert calls[0]["title"].endswith("ligan peringkat 1-2 dari 3 menurut ΔG docking")
    assert calls[1]["title"].endswith("ligan peringkat 3-3 dari 3 menurut ΔG docking")


def test_radar_combined_tanpa_rank_by_memakai_skor_komposit(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    builder.radar_combined(_ROWS, criteria=["affinity_best", "MW", "LogP"], top_n=2)
    assert len(calls[0]["series"]) == 2
    assert calls[0]["title"].endswith("ligan peringkat 1-2 dari 3 menurut skor komposit")


def test_radar_combined_tanpa_catatan_bila_semua_ligan_muat(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    builder.radar_combined(_ROWS, criteria=["affinity_best", "MW", "LogP"], title="Profil", top_n=6)
    assert len(calls) == 1
    assert calls[0]["title"] == "Profil"


def test_radar_combined_normalisasi_global_sama_antar_bagian(tmp_path, monkeypatch):
    """Nilai ternormalisasi tiap ligan tidak bergantung pada bagian tempatnya digambar."""
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    builder.radar_combined(_ROWS, criteria=["affinity_best", "MW", "LogP"], top_n=3)
    together = {s: v for s, v in zip(calls[0]["series"], calls[0]["values"].tolist())}

    calls.clear()
    builder.radar_combined(_ROWS, criteria=["affinity_best", "MW", "LogP"], top_n=1)
    split = {c["series"][0]: c["values"][0].tolist() for c in calls}
    assert split == together


def test_radar_combined_ligan_pinned_ikut_di_setiap_bagian(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    rows = _ROWS + [{"ligand": "NATIVE_X", "affinity_best": -9.0, "MW": 400.0, "LogP": 2.5}]
    builder.radar_combined(rows, criteria=["affinity_best", "MW", "LogP"], top_n=2, rank_by="affinity_best",
                           pinned={"NATIVE_X"})
    assert len(calls) == 3
    assert all("NATIVE_X" in c["series"] and c["pinned"] == {"NATIVE_X"} for c in calls)
    drawn = [s for c in calls for s in c["series"] if s != "NATIVE_X"]
    assert sorted(drawn) == ["A", "B", "C"]


def test_radar_combined_dibatasi_max_pages(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    rows = [{"ligand": f"L{i}", "affinity_best": -float(i), "MW": 100.0 + i, "LogP": 1.0 + 0.1 * i}
            for i in range(1, 11)]
    builder.radar_combined(rows, criteria=["affinity_best", "MW", "LogP"], top_n=2, max_pages=2)
    assert len(calls) == 2


def test_radar_by_category_dibagi_bagian_saat_ligan_melebihi_top_n(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    builder.radar_by_category(_ADMET, "Absorpsi", top_n=2)
    assert calls[0]["title"] == "Profil ADMET: Absorpsi\nligan peringkat 1-2 dari 3 menurut skor tertinggi"
    assert len(calls[0]["series"]) == 2
    assert len(calls) == 2


def test_radar_by_category_tanpa_catatan_saat_semua_ligan_muat(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    calls = _capture_radar(monkeypatch, builder)
    builder.radar_by_category(_ADMET, "Absorpsi")
    assert calls[0]["title"] == "Profil ADMET: Absorpsi"


def test_radar_by_category_absorpsi(tmp_path):
    paths = ChartBuilder(tmp_path).radar_by_category(_ADMET, "Absorpsi")
    assert [p.name for p in paths] == ["radar_admet_absorpsi.png"]
    assert paths[0].exists()


def test_radar_by_category_kurang_dari_3_parameter_return_kosong(tmp_path):
    rows = [{"ligand": "A", "hERG": 0.2, "DILI": 0.1}]
    assert ChartBuilder(tmp_path).radar_by_category(rows, "Toksisitas") == []


def test_radar_by_category_data_kosong_return_kosong(tmp_path):
    assert ChartBuilder(tmp_path).radar_by_category([], "Absorpsi") == []


def test_radar_all_admet_categories_lewati_fisikokimia(tmp_path):
    paths = ChartBuilder(tmp_path).radar_all_admet_categories(_ADMET)
    names = {p.name for p in paths}
    assert "radar_admet_fisikokimia.png" not in names
    assert "radar_admet_absorpsi.png" in names
    assert "radar_admet_toksisitas.png" in names


def test_admet_stacked_bar(tmp_path):
    paths = ChartBuilder(tmp_path).admet_stacked_bar(_ADMET, "Toksisitas")
    assert len(paths) == 1 and paths[0].exists()


def test_admet_stacked_bar_tanpa_parameter_return_kosong(tmp_path):
    assert ChartBuilder(tmp_path).admet_stacked_bar([{"ligand": "A", "KolomAneh": 1}], "Toksisitas") == []


def test_admet_all_stacked_bars(tmp_path):
    names = {p.name for p in ChartBuilder(tmp_path).admet_all_stacked_bars(_ADMET)}
    assert "admet_klasifikasi_absorpsi.png" in names
    assert "admet_klasifikasi_distribusi.png" in names
