"""Test ChemometricPCA: guard minimal 2 kelompok, komputasi 2D/3D dgn data sintetis."""

import numpy as np
import pytest

from chemflow.analytics.pca import ChemometricPCA


def _synthetic_matrix(n_per_group=5, n_features=3):
    """2 kelompok terpisah jelas di ruang fitur -> PC1 harus memisahkan mereka."""
    matrix, labels, groups = [], [], []
    for i in range(n_per_group):
        matrix.append([1.0 + 0.01 * i * (j + 1) for j in range(n_features)])
        labels.append(f"A{i}")
        groups.append("Grup_A")
    for i in range(n_per_group):
        matrix.append([10.0 + 0.01 * i * (j + 1) for j in range(n_features)])
        labels.append(f"B{i}")
        groups.append("Grup_B")
    return matrix, labels, groups


def test_pca_raise_jika_hanya_1_kelompok():
    matrix = [[1, 2], [3, 4], [5, 6]]
    labels = ["X1", "X2", "X3"]
    groups = ["SatuSatunya", "SatuSatunya", "SatuSatunya"]

    pca = ChemometricPCA()
    with pytest.raises(ValueError, match="minimal 2 kelompok"):
        pca.compute(matrix, ["f1", "f2"], labels, groups)


def test_pca_raise_jika_data_kurang_dari_3():
    matrix = [[1, 2], [3, 4]]
    with pytest.raises(ValueError, match="minimal 3 senyawa"):
        ChemometricPCA().compute(matrix, ["f1", "f2"], ["A", "B"], ["G1", "G2"])


def test_pca_raise_jika_n_components_tidak_valid():
    matrix, labels, groups = _synthetic_matrix()
    with pytest.raises(ValueError, match="n_components"):
        ChemometricPCA().compute(matrix, ["f1", "f2", "f3"], labels, groups, n_components=4)


def test_pca_default_3_komponen():
    matrix, labels, groups = _synthetic_matrix(n_features=3)
    result = ChemometricPCA().compute(matrix, ["f1", "f2", "f3"], labels, groups)
    assert result.scores.shape == (10, 3)
    assert result.n_components == 3
    assert len(result.explained_variance_ratio) == 3


def test_pca_2_komponen_eksplisit():
    matrix, labels, groups = _synthetic_matrix(n_features=3)
    result = ChemometricPCA().compute(matrix, ["f1", "f2", "f3"], labels, groups, n_components=2)
    assert result.scores.shape == (10, 2)
    assert result.n_components == 2

    scores_a = [result.scores[i, 0] for i, g in enumerate(result.groups) if g == "Grup_A"]
    scores_b = [result.scores[i, 0] for i, g in enumerate(result.groups) if g == "Grup_B"]
    assert abs(sum(scores_a) / len(scores_a) - sum(scores_b) / len(scores_b)) > 1.0


def test_pca_3_komponen_diturunkan_jika_hanya_2_fitur():
    matrix, labels, groups = _synthetic_matrix(n_features=2)
    result = ChemometricPCA().compute(matrix, ["f1", "f2"], labels, groups, n_components=3)
    assert result.n_components == 2  # diturunkan otomatis, hanya 2 fitur tersedia


def test_plot_2d_menghasilkan_file(tmp_path):
    matrix, labels, groups = _synthetic_matrix()
    pca = ChemometricPCA()
    result = pca.compute(matrix, ["f1", "f2", "f3"], labels, groups)
    out_path = pca.plot_2d(result, tmp_path / "pca_2d.png")
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_plot_3d_menghasilkan_file(tmp_path):
    matrix, labels, groups = _synthetic_matrix()
    pca = ChemometricPCA()
    result = pca.compute(matrix, ["f1", "f2", "f3"], labels, groups)
    out_path = pca.plot_3d(result, tmp_path / "pca_3d.png")
    assert out_path is not None
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_plot_3d_dilewati_jika_hasil_hanya_2_komponen(tmp_path):
    matrix, labels, groups = _synthetic_matrix(n_features=2)
    pca = ChemometricPCA()
    result = pca.compute(matrix, ["f1", "f2"], labels, groups, n_components=2)
    out_path = pca.plot_3d(result, tmp_path / "pca_3d.png")
    assert out_path is None


def test_pca_numpy_fallback_konsisten_dgn_sklearn():
    matrix, labels, groups = _synthetic_matrix()
    pca = ChemometricPCA()
    X_std = pca._standardize(np.array(matrix, dtype=float))

    scores_sklearn, evr_sklearn, _ = pca._pca_sklearn(X_std, 3)
    scores_numpy, evr_numpy, _ = pca._pca_numpy(X_std, 3)

    assert evr_sklearn[0] == pytest.approx(evr_numpy[0], abs=1e-6)
    assert evr_sklearn[2] == pytest.approx(evr_numpy[2], abs=1e-6)
