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


def _series_data():
    rng = np.random.default_rng(3)
    matrix, labels, groups, series = [], [], [], []
    for cls, offset in (("Asli", 0.0), ("Tiruan", 3.0)):
        for ser, shift in (("Aquatic", 0.0), ("Citrus", 1.5)):
            for i in range(4):
                matrix.append(list(rng.normal(offset + shift, 0.4, 5)))
                labels.append(f"{ser[0]}{cls[0]}{i}")
                groups.append(cls)
                series.append(ser)
    return matrix, [f"f{i}" for i in range(5)], labels, groups, series


def test_seri_menjadi_warna_dan_kelas_menjadi_penanda(tmp_path):
    matrix, features, labels, groups, series = _series_data()
    pca = ChemometricPCA()
    result = pca.compute(matrix, features, labels, groups, series=series)
    assert result.series == series and result.color_keys == series
    assert pca.plot_2d(result, tmp_path / "s2.png").stat().st_size > 0
    assert pca.plot_3d(result, tmp_path / "s3.png").stat().st_size > 0


def test_tanpa_seri_warna_mengikuti_kelas():
    matrix, features, labels, groups, _ = _series_data()
    result = ChemometricPCA().compute(matrix, features, labels, groups)
    assert result.series == [] and result.color_keys == groups


def test_panjang_series_harus_sama():
    matrix, features, labels, groups, series = _series_data()
    with pytest.raises(ValueError, match="Panjang"):
        ChemometricPCA().compute(matrix, features, labels, groups, series=series[:-1])


@pytest.mark.parametrize("method", ["auto", "pareto", "center"])
def test_metode_penskalaan_menghasilkan_matriks_berpusat(method):
    from chemflow.analytics.pca import scale_matrix

    X = np.array([[1.0, 100.0], [2.0, 300.0], [3.0, 200.0], [4.0, 400.0]])
    scaled = scale_matrix(X, method)
    assert np.allclose(scaled.mean(axis=0), 0.0)
    if method == "auto":
        assert np.allclose(scaled.std(axis=0), 1.0)
    if method == "center":
        assert np.allclose(scaled, X - X.mean(axis=0))


def test_penskalaan_tidak_dikenal_ditolak():
    from chemflow.analytics.pca import scale_matrix

    with pytest.raises(ValueError, match="penskalaan"):
        scale_matrix(np.ones((3, 2)), "log")


def test_kolom_konstan_tidak_menghasilkan_nan():
    from chemflow.analytics.pca import scale_matrix

    X = np.array([[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]])
    assert np.all(np.isfinite(scale_matrix(X, "auto")))


def test_elips_kepercayaan_mencakup_sebaran():
    from chemflow.analytics.pca import confidence_ellipse

    rng = np.random.default_rng(0)
    points = rng.normal(0, 1, (400, 2)) * [3.0, 1.0]
    center, width, height, angle = confidence_ellipse(points)
    assert width > height
    assert np.allclose(center, points.mean(axis=0))
    assert confidence_ellipse(points[:2]) is None


def test_cincin_3d_berada_di_sekitar_pusat():
    from chemflow.analytics.pca import confidence_ring_3d

    rng = np.random.default_rng(1)
    points = rng.normal(0, 1, (50, 3))
    ring = confidence_ring_3d(points)
    assert ring.shape == (100, 3)
    assert np.allclose(ring.mean(axis=0), points.mean(axis=0), atol=0.05)
    assert confidence_ring_3d(points[:2]) is None


def test_elips_sewarna_penanda_tanpa_seri_dan_abu_abu_bergaris_dengan_seri():
    matrix, features, labels, groups, series = _series_data()
    engine = ChemometricPCA()
    plain = engine.compute(matrix, features, labels, groups)
    from chemflow.analytics.style import group_colors

    colors = group_colors(sorted(set(plain.color_keys)))
    styles = ChemometricPCA._ellipse_styles(plain, sorted(set(groups)), colors)
    assert all(style == (colors[g], "-") for g, style in styles.items())
    with_series = engine.compute(matrix, features, labels, groups, series=series)
    styles = ChemometricPCA._ellipse_styles(with_series, sorted(set(groups)), colors)
    assert {color for color, _ in styles.values()} == {"#333333"}
    assert len({line for _, line in styles.values()}) == 2


def test_label_sumbu_bergaya_jurnal():
    matrix, labels, groups = _synthetic_matrix()
    result = ChemometricPCA().compute(matrix, ["f1", "f2", "f3"], labels, groups)
    label = ChemometricPCA._axis_label(result, 0)
    assert label.startswith("PC1 (") and label.endswith(" %)")
    assert len(label.split("(")[1].split(".")[1].split(" ")[0]) == 2
