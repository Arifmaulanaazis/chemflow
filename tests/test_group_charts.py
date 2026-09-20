"""Test GroupChartBuilder: grafik per grup dengan ligan native sebagai pembanding, termasuk pemotongan otomatis."""

from chemflow.analytics.group_charts import GroupChartBuilder

GROUP_OF = {"A1": "G1", "A2": "G1", "B1": "G2", "B2": "G2", "NATIVE_X": "Native"}

STATS = [
    {"ligand": "A1", "receptor": "R1", "affinity_best": -8.0},
    {"ligand": "A2", "receptor": "R1", "affinity_best": -6.0},
    {"ligand": "B1", "receptor": "R1", "affinity_best": -9.5},
    {"ligand": "B2", "receptor": "R1", "affinity_best": -7.0},
    {"ligand": "NATIVE_X", "receptor": "R1", "affinity_best": -9.0},
    {"ligand": "A1", "receptor": "R2", "affinity_best": -5.0},
    {"ligand": "B1", "receptor": "R2", "affinity_best": -7.5},
    {"ligand": "NATIVE_X", "receptor": "R2", "affinity_best": -8.0},
]

LIPINSKI = [
    {"ligand": "A1", "MW": 180.0, "LogP": 2.0, "HBD": 1, "HBA": 3},
    {"ligand": "A2", "MW": 250.0, "LogP": 3.5, "HBD": 2, "HBA": 5},
    {"ligand": "B1", "MW": 300.0, "LogP": 1.0, "HBD": 0, "HBA": 2},
    {"ligand": "B2", "MW": 320.0, "LogP": 1.5, "HBD": 1, "HBA": 4},
    {"ligand": "NATIVE_X", "MW": 500.0, "LogP": 4.0, "HBD": 3, "HBA": 6},
]

ADMET = [
    {"ligand": "A1", "hERG": 0.1, "DILI": 0.1, "Ames": 0.1, "hia": 0.1, "caco2": -4.5, "pgp_inh": 0.2},
    {"ligand": "A2", "hERG": 0.9, "DILI": 0.9, "Ames": 0.9, "hia": 0.9, "caco2": -6.5, "pgp_inh": 0.8},
    {"ligand": "B1", "hERG": 0.1, "DILI": 0.1, "Ames": 0.1, "hia": 0.1, "caco2": -4.5, "pgp_inh": 0.2},
    {"ligand": "B2", "hERG": 0.2, "DILI": 0.2, "Ames": 0.4, "hia": 0.2, "caco2": -4.8, "pgp_inh": 0.3},
    {"ligand": "NATIVE_X", "hERG": 0.9, "DILI": 0.1, "Ames": 0.1, "hia": 0.3, "caco2": -5.0, "pgp_inh": 0.5},
]


def _names(paths):
    return {p.name for p in paths}


def test_plot_all_menghasilkan_grafik_per_grup(tmp_path):
    paths = GroupChartBuilder(tmp_path).plot_all(STATS, LIPINSKI, ADMET, GROUP_OF)
    names = _names(paths)
    assert {
        "grup_afinitas_box.png", "grup_heatmap_afinitas.png", "grup_heatmap_lebih_baik_dari_native.png",
        "grup_admet_ringkasan.png", "grup_admet_heatmap_toksisitas.png", "grup_admet_radar_toksisitas.png",
        "grup_admet_klasifikasi_toksisitas.png", "grup_fisikokimia_box.png", "grup_radar_gabungan.png",
    } <= names
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


def test_satu_grup_saja_dilewati(tmp_path):
    only = {name: "G1" for name in GROUP_OF}
    assert GroupChartBuilder(tmp_path).plot_all(STATS, LIPINSKI, ADMET, only) == []


def test_tanpa_native_tidak_ada_heatmap_lebih_baik_dari_native(tmp_path):
    group_of = {k: v for k, v in GROUP_OF.items() if v != "Native"}
    stats = [r for r in STATS if r["ligand"] in group_of]
    paths = GroupChartBuilder(tmp_path).plot_all(stats, LIPINSKI, ADMET, group_of)
    names = _names(paths)
    assert "grup_heatmap_afinitas.png" in names
    assert "grup_heatmap_lebih_baik_dari_native.png" not in names


def test_tanpa_admet_dan_lipinski_hanya_grafik_docking(tmp_path):
    names = _names(GroupChartBuilder(tmp_path).plot_all(STATS, [], [], GROUP_OF))
    assert "grup_afinitas_box.png" in names
    assert not any(n.startswith("grup_admet") for n in names)
    assert "grup_fisikokimia_box.png" not in names


def test_grafik_dipotong_bila_grup_banyak(tmp_path):
    group_of = {f"L{i}": f"Grup{i}" for i in range(5)}
    stats = [{"ligand": f"L{i}", "receptor": "R1", "affinity_best": -5.0 - i} for i in range(5)]
    paths = GroupChartBuilder(tmp_path, max_cols=2).affinity_box(stats, group_of)
    assert [p.name for p in paths] == ["grup_afinitas_box_part01of03.png", "grup_afinitas_box_part02of03.png",
                                       "grup_afinitas_box_part03of03.png"]


def test_panel_reseptor_dipotong_per_enam(tmp_path):
    group_of = {"A": "G1", "B": "G2"}
    stats = [{"ligand": lig, "receptor": f"R{i}", "affinity_best": -5.0 - i} for i in range(8) for lig in "AB"]
    paths = GroupChartBuilder(tmp_path).affinity_box(stats, group_of)
    assert len(paths) == 2


def test_klasifikasi_admet_dipotong_per_empat_panel_grup(tmp_path):
    group_of = {f"L{i}": f"G{i}" for i in range(6)}
    admet = [{"ligand": f"L{i}", "hERG": 0.1 * i, "DILI": 0.1, "Ames": 0.1} for i in range(6)]
    paths = GroupChartBuilder(tmp_path).admet_stacked(admet, group_of)
    tox = [p.name for p in paths if "toksisitas" in p.name]
    assert tox == ["grup_admet_klasifikasi_toksisitas_part01of02.png",
                   "grup_admet_klasifikasi_toksisitas_part02of02.png"]


def test_metode_dengan_data_kosong_mengembalikan_list_kosong(tmp_path):
    builder = GroupChartBuilder(tmp_path)
    assert builder.affinity_box([], GROUP_OF) == []
    assert builder.affinity_heatmaps([], GROUP_OF) == []
    assert builder.admet_heatmaps([], GROUP_OF) == []
    assert builder.admet_radars([], GROUP_OF) == []
    assert builder.admet_stacked([], GROUP_OF) == []
    assert builder.physchem_box([], GROUP_OF) == []
    assert builder.combined_radar([], [], [], GROUP_OF) == []


def test_format_svg_ikut_ditulis(tmp_path):
    paths = GroupChartBuilder(tmp_path, formats=("png", "svg")).physchem_box(LIPINSKI, GROUP_OF)
    assert paths[0].with_suffix(".svg").exists()


def test_satu_langkah_gagal_tidak_menghentikan_yang_lain(tmp_path, monkeypatch):
    builder = GroupChartBuilder(tmp_path)

    def rusak(*args, **kwargs):
        raise RuntimeError("simulasi")

    monkeypatch.setattr(builder, "affinity_box", rusak)
    names = _names(builder.plot_all(STATS, LIPINSKI, ADMET, GROUP_OF))
    assert "grup_afinitas_box.png" not in names and "grup_fisikokimia_box.png" in names
