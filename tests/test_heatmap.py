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
    path = builder.heatmap_matrix(matrix, ["baris1", "baris2"], ["kolom1", "kolom2"], "test.png")
    assert path.exists()
    assert path.stat().st_size > 0


def test_heatmap_affinity_pivot_benar(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"receptor": "6LU7", "ligand": "A", "affinity_best": -7.0},
        {"receptor": "6LU7", "ligand": "B", "affinity_best": -5.0},
        {"receptor": "3PTB", "ligand": "A", "affinity_best": -6.0},
    ]
    path = builder.heatmap_affinity(rows)
    assert path is not None
    assert path.exists()


def test_heatmap_affinity_kosong_return_none(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    assert builder.heatmap_affinity([]) is None


def test_heatmap_properties_menghasilkan_file(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"ligand": "A", "MW": 180.0, "LogP": 2.0},
        {"ligand": "B", "MW": 250.0, "LogP": 3.5},
        {"ligand": "C", "MW": 300.0, "LogP": 1.0},
    ]
    path = builder.heatmap_properties(rows, properties=["MW", "LogP"])
    assert path is not None
    assert path.exists()


def test_heatmap_properties_data_tidak_lengkap_return_none(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [{"ligand": "A", "MW": 180.0}]  # kolom "LogP" tak ada
    assert builder.heatmap_properties(rows, properties=["MW", "LogP"]) is None


def test_heatmap_properties_normalize_beda_dari_raw(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"ligand": "A", "MW": 180.0, "LogP": 2.0},
        {"ligand": "B", "MW": 250.0, "LogP": 3.5},
        {"ligand": "C", "MW": 300.0, "LogP": 1.0},
    ]
    path_norm = builder.heatmap_properties(rows, properties=["MW", "LogP"], filename="norm.png", normalize=True)
    path_raw = builder.heatmap_properties(rows, properties=["MW", "LogP"], filename="raw.png", normalize=False)
    assert path_norm.exists() and path_raw.exists()


def test_heatmap_clustered_menghasilkan_file(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([
        [1.0, 1.1, 5.0, 5.2],
        [1.2, 0.9, 4.8, 5.1],
        [5.1, 4.9, 1.0, 1.2],
        [4.9, 5.0, 1.1, 0.9],
    ])
    path = builder.heatmap_clustered(matrix, ["A", "B", "C", "D"], ["p1", "p2", "p3", "p4"])
    assert path is not None
    assert path.exists()
    assert path.stat().st_size > 0


def test_heatmap_clustered_matriks_kosong_return_none(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    assert builder.heatmap_clustered(np.array([]).reshape(0, 0), [], []) is None


def test_heatmap_clustered_mengandung_nan_return_none(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([[1.0, np.nan], [2.0, 3.0], [4.0, 5.0]])
    assert builder.heatmap_clustered(matrix, ["A", "B", "C"], ["p1", "p2"]) is None


def test_heatmap_clustered_kurang_dari_3_baris_tetap_jalan_tanpa_cluster_baris(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    path = builder.heatmap_clustered(matrix, ["A", "B"], ["p1", "p2", "p3"])
    assert path is not None
    assert path.exists()


def test_heatmap_properties_clustered_menghasilkan_file(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [
        {"ligand": "A", "MW": 180.0, "LogP": 2.0, "HBD": 1, "HBA": 3},
        {"ligand": "B", "MW": 250.0, "LogP": 3.5, "HBD": 2, "HBA": 5},
        {"ligand": "C", "MW": 300.0, "LogP": 1.0, "HBD": 0, "HBA": 2},
        {"ligand": "D", "MW": 190.0, "LogP": 2.2, "HBD": 1, "HBA": 3},
    ]
    path = builder.heatmap_properties_clustered(rows, properties=["MW", "LogP", "HBD", "HBA"])
    assert path is not None
    assert path.exists()


def test_heatmap_properties_clustered_data_tidak_lengkap_return_none(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    rows = [{"ligand": "A", "MW": 180.0}]
    assert builder.heatmap_properties_clustered(rows, properties=["MW", "LogP"]) is None


def test_heatmap_clustered_tick_colorbar_dan_cmap_objek(tmp_path):
    from matplotlib.colors import ListedColormap

    builder = HeatmapBuilder(tmp_path)
    matrix = np.array([[1.0, 0.0, 1.0, 0.0], [1.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 1.0], [0.0, 1.0, 1.0, 0.0]])
    path = builder.heatmap_clustered(
        matrix, ["A", "B", "C", "D"], ["r1", "r2", "r3", "r4"], filename="biner.png",
        cmap=ListedColormap(["#F2F2F2", "#0072B2"]), cbar_ticks=[0.25, 0.75], cbar_ticklabels=["Tidak", "Ya"],
        vmin=0.0, vmax=1.0,
    )
    assert path is not None and path.exists()


def test_heatmap_clustered_label_baris_panjang_tetap_dirender(tmp_path):
    builder = HeatmapBuilder(tmp_path)
    matrix = np.random.default_rng(0).random((4, 5))
    labels = ["Ligan dengan nama yang sangat panjang sekali"] * 4
    path = builder.heatmap_clustered(matrix, labels, [f"c{i}" for i in range(5)], filename="panjang.png")
    assert path is not None and path.exists()
