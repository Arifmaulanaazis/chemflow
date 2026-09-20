"""Test HeatmapBuilder: matriks generik, afinitas (reseptor x ligan), properti (ligan x parameter)."""

import numpy as np
import pytest

from chemflow.analytics.heatmap import HeatmapBuilder, format_cell_value


@pytest.mark.parametrize("value, expected", [
    (230.26, "230"), (1234.5, "1234"), (12.04, "12"), (12.5, "12.5"), (3.0, "3"), (3.02, "3.02"),
    (0.06, "0.06"), (0.0, "0"), (-0.001, "0"), (-6.97, "-6.97"), (-11.05, "-11.1"),
])
def test_format_cell_value_tanpa_notasi_ilmiah(value, expected):
    assert format_cell_value(value) == expected


def test_heatmap_matrix_menghasilkan_file(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([[1.0, 2.0], [3.0, np.nan]])
    paths = builder.heatmap_matrix(matrix, ["baris1", "baris2"], ["kolom1", "kolom2"], "test.png")
    assert [p.name for p in paths] == ["test.png"]
    assert paths[0].exists()
    assert paths[0].stat().st_size > 0


def test_heatmap_affinity_pivot_benar(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"receptor": "6LU7", "ligand": "A", "affinity_best": -7.0},
        {"receptor": "6LU7", "ligand": "B", "affinity_best": -5.0},
        {"receptor": "3PTB", "ligand": "A", "affinity_best": -6.0},
    ]
    paths = builder.heatmap_affinity(rows)
    assert [p.name for p in paths] == ["heatmap_afinitas.png"]
    assert paths[0].exists()


def test_heatmap_affinity_kosong_return_list_kosong(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    assert builder.heatmap_affinity([]) == []


def test_heatmap_properties_menghasilkan_file(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"ligand": "A", "MW": 180.0, "LogP": 2.0},
        {"ligand": "B", "MW": 250.0, "LogP": 3.5},
        {"ligand": "C", "MW": 300.0, "LogP": 1.0},
    ]
    paths = builder.heatmap_properties(rows, properties=["MW", "LogP"])
    assert len(paths) == 1
    assert paths[0].exists()


def test_heatmap_properties_data_tidak_lengkap_return_kosong(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [{"ligand": "A", "MW": 180.0}]  # kolom "LogP" tak ada
    assert builder.heatmap_properties(rows, properties=["MW", "LogP"]) == []


def test_heatmap_properties_normalize_beda_dari_raw(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"ligand": "A", "MW": 180.0, "LogP": 2.0},
        {"ligand": "B", "MW": 250.0, "LogP": 3.5},
        {"ligand": "C", "MW": 300.0, "LogP": 1.0},
    ]
    path_norm = builder.heatmap_properties(rows, properties=["MW", "LogP"], filename="norm.png", normalize=True)
    path_raw = builder.heatmap_properties(rows, properties=["MW", "LogP"], filename="raw.png", normalize=False)
    assert path_norm[0].exists() and path_raw[0].exists()


def test_heatmap_clustered_menghasilkan_file(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([
        [1.0, 1.1, 5.0, 5.2],
        [1.2, 0.9, 4.8, 5.1],
        [5.1, 4.9, 1.0, 1.2],
        [4.9, 5.0, 1.1, 0.9],
    ])
    paths = builder.heatmap_clustered(matrix, ["A", "B", "C", "D"], ["p1", "p2", "p3", "p4"])
    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].stat().st_size > 0


def test_heatmap_clustered_matriks_kosong_return_kosong(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    assert builder.heatmap_clustered(np.array([]).reshape(0, 0), [], []) == []


def test_heatmap_clustered_mengandung_nan_return_kosong(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([[1.0, np.nan], [2.0, 3.0], [4.0, 5.0]])
    assert builder.heatmap_clustered(matrix, ["A", "B", "C"], ["p1", "p2"]) == []


def test_heatmap_clustered_kurang_dari_3_baris_tetap_jalan_tanpa_cluster_baris(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    paths = builder.heatmap_clustered(matrix, ["A", "B"], ["p1", "p2", "p3"])
    assert len(paths) == 1
    assert paths[0].exists()


def test_heatmap_properties_clustered_menghasilkan_file(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"ligand": "A", "MW": 180.0, "LogP": 2.0, "HBD": 1, "HBA": 3},
        {"ligand": "B", "MW": 250.0, "LogP": 3.5, "HBD": 2, "HBA": 5},
        {"ligand": "C", "MW": 300.0, "LogP": 1.0, "HBD": 0, "HBA": 2},
        {"ligand": "D", "MW": 190.0, "LogP": 2.2, "HBD": 1, "HBA": 3},
    ]
    paths = builder.heatmap_properties_clustered(rows, properties=["MW", "LogP", "HBD", "HBA"])
    assert len(paths) == 1
    assert paths[0].exists()


def test_heatmap_properties_clustered_data_tidak_lengkap_return_kosong(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [{"ligand": "A", "MW": 180.0}]
    assert builder.heatmap_properties_clustered(rows, properties=["MW", "LogP"]) == []


def test_heatmap_clustered_tick_colorbar_dan_cmap_objek(tmp_path):
    from matplotlib.colors import ListedColormap

    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([[1.0, 0.0, 1.0, 0.0], [1.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 1.0], [0.0, 1.0, 1.0, 0.0]])
    paths = builder.heatmap_clustered(
        matrix, ["A", "B", "C", "D"], ["r1", "r2", "r3", "r4"], filename="biner.png",
        cmap=ListedColormap(["#F2F2F2", "#0072B2"]), cbar_ticks=[0.25, 0.75], cbar_ticklabels=["Tidak", "Ya"],
        vmin=0.0, vmax=1.0,
    )
    assert len(paths) == 1 and paths[0].exists()


def test_heatmap_clustered_label_baris_panjang_tetap_dirender(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.random.default_rng(0).random((4, 5))
    labels = ["Ligan dengan nama yang sangat panjang sekali"] * 4
    paths = builder.heatmap_clustered(matrix, labels, [f"c{i}" for i in range(5)], filename="panjang.png")
    assert len(paths) == 1 and paths[0].exists()


def test_heatmap_matrix_dipotong_menjadi_ubin_baris_x_kolom(tmp_path):
    matrix = np.arange(25, dtype=float).reshape(5, 5)
    builder = HeatmapBuilder(tmp_path, max_rows=3, max_cols=2)
    paths = builder.heatmap_matrix(matrix, list("abcde"), list("vwxyz"), "m.png")
    assert [p.name for p in paths] == [f"m_part0{i}of06.png" for i in range(1, 7)]
    assert all(p.exists() for p in paths)


def test_heatmap_matrix_tanpa_batas_tidak_dipotong(tmp_path):
    matrix = np.arange(100, dtype=float).reshape(10, 10)
    paths = HeatmapBuilder(tmp_path, max_rows=0, max_cols=0).heatmap_matrix(
        matrix, [str(i) for i in range(10)], [str(i) for i in range(10)], "m.png")
    assert [p.name for p in paths] == ["m.png"]


def test_heatmap_matrix_skala_warna_sama_antar_ubin(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    seen = []
    original = plt.Axes.imshow

    def spy(self, *args, **kwargs):
        image = original(self, *args, **kwargs)
        seen.append(image.norm.vmin)
        seen.append(image.norm.vmax)
        return image

    monkeypatch.setattr(plt.Axes, "imshow", spy)
    matrix = np.arange(16, dtype=float).reshape(4, 4)
    HeatmapBuilder(tmp_path, max_rows=2, max_cols=2).heatmap_matrix(
        matrix, list("abcd"), list("wxyz"), "m.png")
    assert set(seen) == {0.0, 15.0}


def test_heatmap_affinity_kolom_native_ikut_di_setiap_ubin(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    captured = []
    original = plt.Axes.set_xticklabels

    def spy(self, labels, *args, **kwargs):
        captured.append([str(t) for t in labels])
        return original(self, labels, *args, **kwargs)

    monkeypatch.setattr(plt.Axes, "set_xticklabels", spy)
    rows = [{"receptor": "R1", "ligand": f"L{i}", "affinity_best": -5.0 - i} for i in range(5)]
    native = [{"receptor": "R1", "ligand": "NATIVE_X", "affinity_best": -9.0}]
    paths = HeatmapBuilder(tmp_path, max_cols=2).heatmap_affinity(rows, native_rows=native)
    assert len(paths) == 3
    assert all(labels[0] == "Native (ref)" for labels in captured)


def test_heatmap_clustered_dipotong_menjadi_bagian(tmp_path):
    matrix = np.random.default_rng(1).random((8, 4))
    labels = [f"L{i}" for i in range(8)]
    paths = HeatmapBuilder(tmp_path, max_rows=3).heatmap_clustered(matrix, labels, ["a", "b", "c", "d"], "k.png")
    assert [p.name for p in paths] == ["k_part01of03.png", "k_part02of03.png", "k_part03of03.png"]
    assert all(p.exists() for p in paths)


def test_heatmap_properties_label_diwarnai_per_grup(tmp_path):
    rows = [{"ligand": "A", "MW": 1.0, "LogP": 2.0}, {"ligand": "B", "MW": 2.0, "LogP": 1.0},
            {"ligand": "C", "MW": 3.0, "LogP": 0.5}]
    paths = HeatmapBuilder(tmp_path).heatmap_properties(
        rows, properties=["MW", "LogP"], row_groups={"A": "G1", "B": "G2", "C": "Native"})
    assert paths[0].exists()
