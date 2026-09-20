"""Test statistik GC-MS: FDR, uji univariat, PLS-DA, LDA, VIP, kemiripan, RSD, pencilan."""

import numpy as np
import pytest

from chemflow.gcms import stats


def _two_class_data(n_per_class=8, n_features=12, seed=0):
    """Fitur 0 membedakan kelas dengan tegas; sisanya derau."""
    rng = np.random.default_rng(seed)
    X = rng.normal(10.0, 1.0, (2 * n_per_class, n_features))
    X[n_per_class:, 0] += 8.0
    labels = ["Asli"] * n_per_class + ["Tiruan"] * n_per_class
    return X, labels


def test_benjamini_hochberg_nilai_tetap():
    q = stats.benjamini_hochberg([0.01, 0.04, 0.03, 0.005])
    assert q.tolist() == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_benjamini_hochberg_mempertahankan_nan_dan_batas_satu():
    q = stats.benjamini_hochberg([0.5, np.nan, 0.9])
    assert np.isnan(q[1]) and q[0] <= 1.0 and q[2] <= 1.0
    assert np.isnan(stats.benjamini_hochberg([np.nan, np.nan])).all()


def test_blocker_terawasi():
    assert "satu kelas" in stats.supervised_blocker(["a"] * 8)
    assert "satu sampel" in stats.supervised_blocker(["a"] * 5 + ["b"])
    assert "terlalu sedikit" in stats.supervised_blocker(["a", "a", "b", "b"])
    assert stats.supervised_blocker(["a"] * 4 + ["b"] * 4) is None


def test_univariat_dua_kelas_menemukan_penanda():
    X, labels = _two_class_data()
    names = [f"f{i}" for i in range(X.shape[1])]
    table = stats.univariate_tests(X, labels, names)
    top = table.sort_values("q_welch").iloc[0]
    assert top["feature"] == "f0" and top["q_welch"] < 1e-6 and top["log2_fold_change"] > 0
    assert top["cohen_d"] > 3 and top["eta_squared"] > 0.8
    assert (table[table["feature"] != "f0"]["q_welch"] > 0.05).sum() >= 9
    assert {"p_welch", "p_mannwhitney", "q_welch", "q_mannwhitney", "mean_Asli", "mean_Tiruan"} <= set(table.columns)


def test_univariat_tiga_kelas_memakai_anova_dan_kruskal():
    rng = np.random.default_rng(1)
    X = rng.normal(0, 1, (18, 4))
    X[6:12, 1] += 6.0
    X[12:, 1] += 12.0
    table = stats.univariate_tests(X, ["a"] * 6 + ["b"] * 6 + ["c"] * 6, ["w", "x", "y", "z"])
    assert {"p_anova", "q_anova", "p_kruskal", "q_kruskal"} <= set(table.columns)
    assert "p_welch" not in table.columns
    assert table.sort_values("p_anova").iloc[0]["feature"] == "x"


def test_univariat_log2fc_memakai_matriks_mentah_bila_diberikan():
    X = np.log10(np.array([[1.0], [1.0], [4.0], [4.0]]) + 0.5)
    raw = np.array([[1.0], [1.0], [4.0], [4.0]])
    table = stats.univariate_tests(X, ["a", "a", "b", "b"], ["f"], raw=raw)
    assert table["log2_fold_change"].iloc[0] == pytest.approx(np.log2((4.0 + 0.5) / (1.0 + 0.5)))


def test_univariat_kelas_satu_sampel_menghasilkan_nan_bukan_error():
    table = stats.univariate_tests(np.array([[1.0], [2.0], [3.0]]), ["a", "b", "c"], ["f"])
    assert np.isnan(table["p_anova"].iloc[0])


def test_pls_da_memisahkan_kelas_dan_vip_menunjuk_penanda():
    X, labels = _two_class_data()
    result = stats.pls_da(X, labels, n_permutations=60, seed=0)
    assert result.accuracy == 1.0 and result.balanced_accuracy == 1.0 and result.q2 > 0.7
    assert result.permutation_p < 0.05 and result.permuted_accuracy.size == 60
    assert int(np.argmax(result.vip)) == 0 and result.vip[0] > 1.0
    assert result.confusion.to_numpy().trace() == len(labels)
    assert result.scores.shape[0] == len(labels) and 0 < sum(result.explained_x) <= 1.0001


def test_pls_da_derau_tidak_dikira_terpisah():
    rng = np.random.default_rng(5)
    X = rng.normal(0, 1, (16, 30))
    result = stats.pls_da(X, ["a"] * 8 + ["b"] * 8, n_permutations=60, seed=1)
    assert result.permutation_p > 0.05


def test_pls_da_tanpa_permutasi_dan_penolakan_data_kurang():
    X, labels = _two_class_data()
    result = stats.pls_da(X, labels, n_permutations=0)
    assert np.isnan(result.permutation_p) and result.permuted_accuracy.size == 0
    with pytest.raises(ValueError, match="tidak bisa dijalankan"):
        stats.pls_da(X[:4], labels[:4])
    with pytest.raises(ValueError, match="Penskalaan"):
        stats.pls_da(X, labels, scaling="log")


def test_pls_da_tiga_kelas():
    rng = np.random.default_rng(2)
    X = rng.normal(0, 1, (24, 10))
    X[8:16, 2] += 7.0
    X[16:, 5] += 7.0
    result = stats.pls_da(X, ["a"] * 8 + ["b"] * 8 + ["c"] * 8, n_permutations=30)
    assert result.accuracy > 0.9 and result.confusion.shape == (3, 3)


def test_lda_cv_dan_reprodusibel_dengan_seed_sama():
    X, labels = _two_class_data()
    first = stats.lda_cv(X, labels, n_permutations=40, seed=3)
    again = stats.lda_cv(X, labels, n_permutations=40, seed=3)
    assert first.accuracy == 1.0 and first.method == "LDA"
    assert first.permutation_p == again.permutation_p and first.accuracy == again.accuracy
    with pytest.raises(ValueError, match="tidak bisa dijalankan"):
        stats.lda_cv(X[:5], labels[:5])


def test_skala_dihitung_dari_data_latih_tanpa_kebocoran():
    scale = stats._fit_scaler(np.array([[0.0], [2.0], [4.0]]), "auto")
    assert scale(np.array([[2.0]]))[0, 0] == pytest.approx(0.0)
    assert scale(np.array([[4.0]]))[0, 0] == pytest.approx(2.0 / np.std([0.0, 2.0, 4.0]))


def test_kemiripan_kosinus_dan_pearson():
    X = np.array([[1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [3.0, 2.0, 1.0]])
    cosine = stats.similarity_matrix(X, ["a", "b", "c"], "cosine")
    pearson = stats.similarity_matrix(X, ["a", "b", "c"], "pearson")
    assert cosine.loc["a", "b"] == pytest.approx(1.0) and cosine.loc["a", "c"] < 0.8
    assert pearson.loc["a", "c"] == pytest.approx(-1.0) and list(cosine.index) == ["a", "b", "c"]
    with pytest.raises(ValueError, match="cosine"):
        stats.similarity_matrix(X, ["a", "b", "c"], "euclid")


def test_rsd_ulangan_dan_kelompok_tunggal_dilewati():
    X = np.array([[10.0, 1.0], [12.0, 1.0], [11.0, 1.0], [5.0, 9.0]])
    table = stats.replicate_rsd(X, ["A", "A", "A", "B"], ["f1", "f2"])
    assert list(table.columns) == ["A"]
    assert table.loc["f1", "A"] == pytest.approx(100 * np.std([10, 12, 11], ddof=1) / 11)
    assert table.loc["f2", "A"] == pytest.approx(0.0)


def test_hotelling_t2_menandai_pencilan():
    rng = np.random.default_rng(0)
    scores = rng.normal(0, 1, (20, 2))
    scores[0] = [9.0, 9.0]
    table = stats.hotelling_t2(scores, [f"s{i}" for i in range(20)])
    assert table.loc[table["outlier"], "sample"].tolist() == ["s0"]
    assert table["limit_95"].iloc[0] > 0


def test_hotelling_t2_sampel_terlalu_sedikit_tanpa_batas():
    table = stats.hotelling_t2(np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 7.0]]), ["a", "b", "c"])
    assert np.isnan(table["limit_95"].iloc[0]) and not table["outlier"].any()
