"""Test HierarchicalClustering (HCA): linkage, cluster assignment, dendrogram."""

import numpy as np
import pytest

from chemflow.analytics.hca import HierarchicalClustering


def _synthetic_matrix():
    matrix, labels, groups = [], [], []
    for i in range(4):
        matrix.append([1.0 + 0.01 * i, 2.0 + 0.01 * i])
        labels.append(f"A{i}")
        groups.append("Grup_A")
    for i in range(4):
        matrix.append([10.0 + 0.01 * i, 20.0 + 0.01 * i])
        labels.append(f"B{i}")
        groups.append("Grup_B")
    return matrix, labels, groups


def test_compute_raise_jika_kurang_dari_2_senyawa():
    hca = HierarchicalClustering()
    with pytest.raises(ValueError, match="minimal 2 senyawa"):
        hca.compute([[1, 2]], ["A"])


def test_compute_menghasilkan_linkage_matrix():
    matrix, labels, groups = _synthetic_matrix()
    result = HierarchicalClustering().compute(matrix, labels, groups)
    assert result.linkage_matrix.shape == (len(labels) - 1, 4)
    assert result.labels == labels


def test_assign_clusters_2_klaster_pisahkan_grup():
    matrix, labels, groups = _synthetic_matrix()
    hca = HierarchicalClustering()
    result = hca.compute(matrix, labels, groups)
    assignment = hca.assign_clusters(result, n_clusters=2)

    cluster_a = {assignment[l] for l in labels if l.startswith("A")}
    cluster_b = {assignment[l] for l in labels if l.startswith("B")}
    assert len(cluster_a) == 1
    assert len(cluster_b) == 1
    assert cluster_a != cluster_b


def test_plot_dendrogram_menghasilkan_file(tmp_path):
    matrix, labels, groups = _synthetic_matrix()
    hca = HierarchicalClustering()
    result = hca.compute(matrix, labels, groups)
    paths = hca.plot_dendrogram(result, tmp_path / "dendro.png")
    assert [p.name for p in paths] == ["dendro.png"]
    assert paths[0].exists()
    assert paths[0].stat().st_size > 0


def test_plot_dendrogram_tanpa_grup_tidak_error(tmp_path):
    matrix, labels, _ = _synthetic_matrix()
    hca = HierarchicalClustering()
    result = hca.compute(matrix, labels)  # groups=None
    paths = hca.plot_dendrogram(result, tmp_path / "dendro.png", color_by_group=True)
    assert paths[0].exists()


def test_plot_dendrogram_dipotong_menjadi_jendela_daun(tmp_path):
    matrix, labels, groups = _synthetic_matrix()
    hca = HierarchicalClustering()
    result = hca.compute(matrix, labels, groups)
    paths = hca.plot_dendrogram(result, tmp_path / "dendro.png", max_leaves=3)
    assert [p.name for p in paths] == ["dendro_part01of03.png", "dendro_part02of03.png", "dendro_part03of03.png"]
    assert all(p.exists() for p in paths)


def test_plot_dendrogram_tanpa_batas_satu_gambar(tmp_path):
    matrix, labels, groups = _synthetic_matrix()
    hca = HierarchicalClustering()
    result = hca.compute(matrix, labels, groups)
    assert len(hca.plot_dendrogram(result, tmp_path / "dendro.png", max_leaves=0)) == 1


def test_standardize_hasil_mean_nol_std_satu():
    X = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
    X_std = HierarchicalClustering._standardize(X)
    assert np.allclose(X_std.mean(axis=0), 0.0, atol=1e-10)
    assert np.allclose(X_std.std(axis=0), 1.0, atol=1e-10)
