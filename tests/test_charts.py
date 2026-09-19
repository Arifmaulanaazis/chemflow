"""Test ChartBuilder: bar, radar gabungan, radar dan bar klasifikasi ADMET."""

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


def test_bar_affinity_menghasilkan_file(tmp_path):
    path = ChartBuilder(tmp_path).bar_affinity(_ROWS)
    assert path.exists() and path.stat().st_size > 0


def test_bar_affinity_top_n(tmp_path):
    rows = [{"ligand": f"L{i}", "affinity_best": -float(i)} for i in range(1, 11)]
    assert ChartBuilder(tmp_path).bar_affinity(rows, top_n=3, filename="top3.png").exists()


def test_bar_affinity_nilai_positif_dan_negatif(tmp_path):
    rows = [{"ligand": "A", "affinity_best": -7.0}, {"ligand": "B", "affinity_best": 1.5}]
    assert ChartBuilder(tmp_path).bar_affinity(rows).exists()


def test_format_tambahan_svg_pdf_ditulis_berdampingan(tmp_path):
    path = ChartBuilder(tmp_path, formats=("png", "svg", "pdf")).bar_affinity(_ROWS)
    assert path.with_suffix(".svg").exists()
    assert path.with_suffix(".pdf").exists()


def test_radar_combined_menghasilkan_file(tmp_path):
    path = ChartBuilder(tmp_path).radar_combined(
        _ROWS, criteria=["affinity_best", "MW", "LogP"], lower_is_better=["affinity_best"],
        criteria_labels={"affinity_best": "ΔG docking"},
    )
    assert path is not None and path.exists()


def test_radar_combined_kriteria_absolut_tanpa_minmax(tmp_path):
    rows = [{**r, "Absorpsi": s} for r, s in zip(_ROWS, (1.0, 0.5, 0.0))]
    path = ChartBuilder(tmp_path).radar_combined(
        rows, criteria=["affinity_best", "MW", "Absorpsi"], absolute=["Absorpsi"],
    )
    assert path is not None


def test_radar_combined_data_tidak_lengkap_return_none(tmp_path):
    rows = [{"ligand": "A", "affinity_best": -7.0}]
    assert ChartBuilder(tmp_path).radar_combined(rows, criteria=["affinity_best", "MW", "LogP"]) is None


def test_radar_combined_kurang_dari_3_kriteria_return_none(tmp_path):
    assert ChartBuilder(tmp_path).radar_combined(_ROWS, criteria=["affinity_best", "MW"]) is None


def _capture_radar(monkeypatch, builder):
    captured = {}

    def fake_draw(values, series_labels, axis_labels, title, **kwargs):
        captured.update(values=values, series=series_labels, axes=axis_labels, title=title)
        return builder._dir / "x.png"

    monkeypatch.setattr(builder, "_draw_radar", fake_draw)
    return captured


def test_radar_combined_peringkat_menurut_kriteria(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    captured = _capture_radar(monkeypatch, builder)
    builder.radar_combined(
        _ROWS, criteria=["affinity_best", "MW", "LogP"], lower_is_better=["affinity_best"],
        criteria_labels={"affinity_best": "ΔG docking"}, top_n=2, rank_by="affinity_best",
    )
    assert captured["series"] == ["A", "C"]
    assert captured["title"].endswith("2 dari 3 ligan dengan ΔG docking terbaik")


def test_radar_combined_tanpa_rank_by_memakai_skor_komposit(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    captured = _capture_radar(monkeypatch, builder)
    builder.radar_combined(_ROWS, criteria=["affinity_best", "MW", "LogP"], top_n=2)
    assert len(captured["series"]) == 2
    assert captured["title"].endswith("2 dari 3 ligan dengan skor komposit terbaik")


def test_radar_combined_tanpa_catatan_bila_semua_ligan_muat(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    captured = _capture_radar(monkeypatch, builder)
    builder.radar_combined(_ROWS, criteria=["affinity_best", "MW", "LogP"], title="Profil", top_n=6)
    assert captured["title"] == "Profil"


def test_radar_by_category_catatan_judul_saat_ligan_dipangkas(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    captured = _capture_radar(monkeypatch, builder)
    builder.radar_by_category(_ADMET, "Absorpsi", top_n=2)
    assert captured["title"] == "Profil ADMET: Absorpsi\n2 dari 3 ligan dengan skor tertinggi"
    assert len(captured["series"]) == 2


def test_radar_by_category_tanpa_catatan_saat_semua_ligan_muat(tmp_path, monkeypatch):
    builder = ChartBuilder(tmp_path)
    captured = _capture_radar(monkeypatch, builder)
    builder.radar_by_category(_ADMET, "Absorpsi")
    assert captured["title"] == "Profil ADMET: Absorpsi"


def test_radar_by_category_absorpsi(tmp_path):
    path = ChartBuilder(tmp_path).radar_by_category(_ADMET, "Absorpsi")
    assert path is not None and path.name == "radar_admet_absorpsi.png"
    assert path.exists()


def test_radar_by_category_kurang_dari_3_parameter_return_none(tmp_path):
    rows = [{"ligand": "A", "hERG": 0.2, "DILI": 0.1}]
    assert ChartBuilder(tmp_path).radar_by_category(rows, "Toksisitas") is None


def test_radar_by_category_data_kosong_return_none(tmp_path):
    assert ChartBuilder(tmp_path).radar_by_category([], "Absorpsi") is None


def test_radar_all_admet_categories_lewati_fisikokimia(tmp_path):
    paths = ChartBuilder(tmp_path).radar_all_admet_categories(_ADMET)
    names = {p.name for p in paths}
    assert "radar_admet_fisikokimia.png" not in names
    assert "radar_admet_absorpsi.png" in names
    assert "radar_admet_toksisitas.png" in names


def test_admet_stacked_bar(tmp_path):
    path = ChartBuilder(tmp_path).admet_stacked_bar(_ADMET, "Toksisitas")
    assert path is not None and path.exists()


def test_admet_stacked_bar_tanpa_parameter_return_none(tmp_path):
    assert ChartBuilder(tmp_path).admet_stacked_bar([{"ligand": "A", "KolomAneh": 1}], "Toksisitas") is None


def test_admet_all_stacked_bars(tmp_path):
    names = {p.name for p in ChartBuilder(tmp_path).admet_all_stacked_bars(_ADMET)}
    assert "admet_klasifikasi_absorpsi.png" in names
    assert "admet_klasifikasi_distribusi.png" in names
