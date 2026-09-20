"""
Statistik komparatif GC-MS: uji univariat dengan koreksi FDR, klasifikasi terawasi
(PLS-DA dan LDA) dengan validasi silang dan uji permutasi, skor VIP, kemiripan antar
sampel, presisi ulangan, dan deteksi pencilan Hotelling T2.

Penskalaan dihitung ulang di dalam tiap lipatan validasi silang (parameter dari data
latih, diterapkan ke data uji) agar akurasi tidak menggelembung oleh kebocoran data.
"""

from __future__ import annotations

import warnings
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats as sps

from chemflow.analytics.pca import SCALING_METHODS


@dataclass
class ClassificationResult:
    """Ringkasan satu model terawasi (PLS-DA atau LDA) yang divalidasi silang."""
    method: str
    labels: List[str]
    accuracy: float
    balanced_accuracy: float
    confusion: pd.DataFrame                  # baris kelas sebenarnya, kolom kelas terprediksi
    n_components: int
    n_splits: int
    q2: float = float("nan")
    permutation_p: float = float("nan")
    n_permutations: int = 0
    permuted_accuracy: np.ndarray = field(default_factory=lambda: np.empty(0))
    vip: Optional[np.ndarray] = None
    scores: Optional[np.ndarray] = None      # skor model pada seluruh data
    explained_x: Optional[Tuple[float, ...]] = None


def benjamini_hochberg(p_values: Sequence[float]) -> np.ndarray:
    """Nilai q (FDR Benjamini-Hochberg); NaN dipertahankan dan tidak dihitung."""
    p = np.asarray(p_values, dtype=float)
    q = np.full(p.shape, np.nan)
    valid = np.isfinite(p)
    if not valid.any():
        return q
    order = np.argsort(p[valid])
    ranked = p[valid][order] * valid.sum() / (np.arange(valid.sum()) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    result = np.empty(valid.sum())
    result[order] = np.clip(ranked, 0.0, 1.0)
    q[valid] = result
    return q


def supervised_blocker(labels: Sequence[str]) -> Optional[str]:
    """Alasan model terawasi tidak bisa dijalankan, atau ``None`` bila data cukup."""
    counts = Counter(labels)
    if len(counts) < 2:
        return "hanya satu kelas"
    small = [name for name, n in counts.items() if n < 2]
    if small:
        return f"kelas dengan satu sampel: {', '.join(map(str, small))}"
    if len(labels) < 6:
        return f"sampel terlalu sedikit ({len(labels)}), minimal 6"
    return None


# ---------------------------------------------------------------- univariat

def univariate_tests(X: np.ndarray, labels: Sequence[str], feature_names: Sequence[str],
                     raw: Optional[np.ndarray] = None) -> pd.DataFrame:
    """Uji tiap fitur antar kelas.

    Untuk 2 kelas: Welch t dan Mann-Whitney U, log2 fold change (dari ``raw``), dan d Cohen.
    Untuk 3 kelas atau lebih: ANOVA satu arah dan Kruskal-Wallis. Selalu ada ukuran efek eta kuadrat
    dan nilai q (BH) tiap uji. ``X`` adalah matriks yang diuji (mis. setelah transformasi), ``raw``
    matriks yang dipakai menghitung rata-rata dan fold change (bawaan ``X``).
    """
    X = np.asarray(X, dtype=float)
    raw = X if raw is None else np.asarray(raw, dtype=float)
    labels = np.asarray(labels)
    classes = sorted(set(labels))
    positive = raw[raw > 0]
    pseudo = 0.5 * float(positive.min()) if positive.size else 1.0
    rows: List[Dict[str, object]] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for j, feature in enumerate(feature_names):
            groups = [X[labels == c, j] for c in classes]
            raw_groups = [raw[labels == c, j] for c in classes]
            row: Dict[str, object] = {"feature": feature}
            for c, values in zip(classes, raw_groups):
                row[f"mean_{c}"] = float(values.mean())
            grand = X[:, j].mean()
            ss_total = float(((X[:, j] - grand) ** 2).sum())
            ss_between = float(sum(len(g) * (g.mean() - grand) ** 2 for g in groups))
            row["eta_squared"] = ss_between / ss_total if ss_total > 0 else float("nan")
            testable = [g for g in groups if len(g) >= 1]
            enough = sum(len(g) >= 2 for g in groups) >= 1 and len(testable) >= 2 and X.shape[0] > len(classes)
            if len(classes) == 2:
                a, b = groups
                row["log2_fold_change"] = float(np.log2((raw_groups[1].mean() + pseudo) / (raw_groups[0].mean() + pseudo)))
                pooled = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / max(len(a) + len(b) - 2, 1)) \
                    if len(a) > 1 and len(b) > 1 else float("nan")
                row["cohen_d"] = float((b.mean() - a.mean()) / pooled) if pooled and np.isfinite(pooled) and pooled > 0 else float("nan")
                row["p_welch"] = float(sps.ttest_ind(a, b, equal_var=False).pvalue) if enough and len(a) > 1 and len(b) > 1 else float("nan")
                try:
                    row["p_mannwhitney"] = float(sps.mannwhitneyu(a, b, alternative="two-sided").pvalue) if enough else float("nan")
                except ValueError:
                    row["p_mannwhitney"] = float("nan")
            else:
                row["p_anova"] = float(sps.f_oneway(*groups).pvalue) if enough and all(len(g) >= 1 for g in groups) else float("nan")
                try:
                    row["p_kruskal"] = float(sps.kruskal(*groups).pvalue) if enough else float("nan")
                except ValueError:
                    row["p_kruskal"] = float("nan")
            rows.append(row)
    table = pd.DataFrame(rows)
    for column in [c for c in table.columns if c.startswith("p_")]:
        table["q_" + column[2:]] = benjamini_hochberg(table[column].to_numpy())
    return table


# ---------------------------------------------------------------- terawasi

def _fit_scaler(X: np.ndarray, method: str) -> Callable[[np.ndarray], np.ndarray]:
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    divisor = {"auto": std, "pareto": np.sqrt(std), "center": np.ones_like(std)}[method]
    return lambda data: (data - mean) / divisor


def _folds(y: np.ndarray, n_splits: int, seed: int) -> List[Tuple[np.ndarray, np.ndarray]]:
    from sklearn.model_selection import StratifiedKFold

    return list(StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed).split(np.zeros(len(y)), y))


def _predict_cv(X: np.ndarray, y: np.ndarray, scaling: str, folds, fit_predict) -> np.ndarray:
    """Prediksi luar-lipatan; ``fit_predict(Xtrain, ytrain, Xtest)`` mengembalikan skor atau label."""
    out = None
    for train, test in folds:
        scale = _fit_scaler(X[train], scaling)
        result = fit_predict(scale(X[train]), y[train], scale(X[test]))
        if out is None:
            out = np.zeros((len(y),) + np.shape(result)[1:], dtype=float)
        out[test] = result
    return out


def _accuracy_stats(y: np.ndarray, predicted: np.ndarray, classes: int) -> Tuple[float, float, np.ndarray]:
    matrix = np.zeros((classes, classes), dtype=int)
    for truth, guess in zip(y, predicted):
        matrix[truth, guess] += 1
    recall = [matrix[i, i] / matrix[i].sum() for i in range(classes) if matrix[i].sum() > 0]
    return float(np.trace(matrix) / matrix.sum()), float(np.mean(recall)), matrix


def _folds_for(y: np.ndarray, requested: Optional[int]) -> int:
    smallest = int(np.bincount(y).min())
    return max(2, min(requested or 5, smallest))


def _pls_fit_predict(n_components: int, n_classes: int):
    from sklearn.cross_decomposition import PLSRegression

    def run(Xtrain, ytrain, Xtest):
        Y = np.eye(n_classes)[ytrain]
        k = max(1, min(n_components, Xtrain.shape[0] - 1, Xtrain.shape[1]))
        model = PLSRegression(n_components=k, scale=False).fit(Xtrain, Y)
        return model.predict(Xtest)
    return run


def vip_scores(model) -> np.ndarray:
    """Variable Importance in Projection dari model ``PLSRegression`` yang sudah dilatih."""
    t, w, q = model.x_scores_, model.x_weights_, model.y_loadings_
    p = w.shape[0]
    ss = np.sum(q ** 2, axis=0) * np.sum(t ** 2, axis=0)
    weight = w / np.maximum(np.linalg.norm(w, axis=0, keepdims=True), 1e-12)
    return np.sqrt(p * (weight ** 2 @ ss) / max(ss.sum(), 1e-12))


def _permute(score_fn: Callable[[np.ndarray], float], y: np.ndarray, observed: float, n: int, seed: int) -> Tuple[float, np.ndarray]:
    rng = np.random.default_rng(seed)
    permuted = np.array([score_fn(rng.permutation(y)) for _ in range(n)])
    return float((np.sum(permuted >= observed) + 1) / (n + 1)), permuted


def pls_da(X: np.ndarray, labels: Sequence[str], scaling: str = "pareto", max_components: int = 5,
           n_splits: Optional[int] = None, n_permutations: int = 200, seed: int = 0) -> ClassificationResult:
    """PLS-DA dengan jumlah komponen dipilih lewat Q2 validasi silang, akurasi CV, VIP, dan uji permutasi.

    Raises:
        ValueError: data tidak memenuhi syarat (lihat ``supervised_blocker``) atau penskalaan tidak dikenal.
    """
    from sklearn.cross_decomposition import PLSRegression

    if scaling not in SCALING_METHODS:
        raise ValueError(f"Penskalaan harus salah satu dari {SCALING_METHODS}, dapat: {scaling!r}")
    reason = supervised_blocker(labels)
    if reason:
        raise ValueError(f"PLS-DA tidak bisa dijalankan: {reason}.")
    X = np.asarray(X, dtype=float)
    classes = sorted(set(labels))
    y = np.array([classes.index(label) for label in labels])
    folds = _folds(y, _folds_for(y, n_splits), seed)
    Y = np.eye(len(classes))[y]
    total_ss = float(((Y - Y.mean(axis=0)) ** 2).sum())

    best_k, best_q2 = 1, -np.inf
    for k in range(1, max(1, min(max_components, X.shape[0] - 2, X.shape[1])) + 1):
        predicted = _predict_cv(X, y, scaling, folds, _pls_fit_predict(k, len(classes)))
        q2 = 1.0 - float(((Y - predicted) ** 2).sum()) / total_ss
        if q2 > best_q2 + 1e-9:
            best_k, best_q2 = k, q2

    predicted = _predict_cv(X, y, scaling, folds, _pls_fit_predict(best_k, len(classes)))
    accuracy, balanced, matrix = _accuracy_stats(y, predicted.argmax(axis=1), len(classes))

    def permuted_score(shuffled: np.ndarray) -> float:
        guess = _predict_cv(X, shuffled, scaling, _folds(shuffled, _folds_for(shuffled, n_splits), seed),
                            _pls_fit_predict(best_k, len(classes)))
        return float(np.mean(guess.argmax(axis=1) == shuffled))

    p_value, permuted = (_permute(permuted_score, y, accuracy, n_permutations, seed) if n_permutations > 0
                         else (float("nan"), np.empty(0)))
    scaled = _fit_scaler(X, scaling)(X)
    model = PLSRegression(n_components=best_k, scale=False).fit(scaled, Y)
    per_component = np.sum(model.x_loadings_ ** 2, axis=0) * np.var(model.x_scores_, axis=0, ddof=1)
    explained = tuple((per_component / max(np.sum(scaled ** 2) / max(X.shape[0] - 1, 1), 1e-12)).tolist())
    return ClassificationResult(
        method="PLS-DA", labels=classes, accuracy=accuracy, balanced_accuracy=balanced,
        confusion=pd.DataFrame(matrix, index=classes, columns=classes), n_components=best_k,
        n_splits=len(folds), q2=best_q2, permutation_p=p_value, n_permutations=n_permutations,
        permuted_accuracy=permuted, vip=vip_scores(model), scores=model.x_scores_, explained_x=explained,
    )


def _lda_fit_predict(n_components: int):
    from sklearn.decomposition import PCA
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

    def run(Xtrain, ytrain, Xtest):
        k = max(1, min(n_components, Xtrain.shape[0] - 1, Xtrain.shape[1]))
        pca = PCA(n_components=k).fit(Xtrain)
        model = LinearDiscriminantAnalysis().fit(pca.transform(Xtrain), ytrain)
        return model.predict(pca.transform(Xtest))
    return run


def lda_cv(X: np.ndarray, labels: Sequence[str], scaling: str = "pareto", n_components: int = 10,
           n_splits: Optional[int] = None, n_permutations: int = 200, seed: int = 0) -> ClassificationResult:
    """LDA pada skor PCA (mencegah matriks kovarians singular) dengan akurasi validasi silang dan uji permutasi."""
    if scaling not in SCALING_METHODS:
        raise ValueError(f"Penskalaan harus salah satu dari {SCALING_METHODS}, dapat: {scaling!r}")
    reason = supervised_blocker(labels)
    if reason:
        raise ValueError(f"LDA tidak bisa dijalankan: {reason}.")
    X = np.asarray(X, dtype=float)
    classes = sorted(set(labels))
    y = np.array([classes.index(label) for label in labels])
    folds = _folds(y, _folds_for(y, n_splits), seed)
    k = max(1, min(n_components, X.shape[0] // 3, X.shape[1]))   # sampel per dimensi tetap cukup agar LDA tidak overfit
    guess = _predict_cv(X, y, scaling, folds, _lda_fit_predict(k)).astype(int)
    accuracy, balanced, matrix = _accuracy_stats(y, guess, len(classes))

    def permuted_score(shuffled: np.ndarray) -> float:
        got = _predict_cv(X, shuffled, scaling, _folds(shuffled, _folds_for(shuffled, n_splits), seed), _lda_fit_predict(k))
        return float(np.mean(got.astype(int) == shuffled))

    p_value, permuted = (_permute(permuted_score, y, accuracy, n_permutations, seed) if n_permutations > 0
                         else (float("nan"), np.empty(0)))
    return ClassificationResult(
        method="LDA", labels=classes, accuracy=accuracy, balanced_accuracy=balanced,
        confusion=pd.DataFrame(matrix, index=classes, columns=classes), n_components=k, n_splits=len(folds),
        permutation_p=p_value, n_permutations=n_permutations, permuted_accuracy=permuted,
    )


# ---------------------------------------------------------------- kemiripan, presisi, pencilan

def similarity_matrix(X: np.ndarray, labels: Sequence[str], method: str = "cosine") -> pd.DataFrame:
    """Kemiripan antar sampel: ``cosine`` atau ``pearson`` (keduanya 1 berarti identik)."""
    X = np.asarray(X, dtype=float)
    if method == "cosine":
        norm = np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
        matrix = (X / norm) @ (X / norm).T
    elif method == "pearson":
        matrix = np.corrcoef(X)
    else:
        raise ValueError(f"Metode kemiripan harus 'cosine' atau 'pearson', dapat: {method!r}")
    return pd.DataFrame(np.nan_to_num(matrix), index=list(labels), columns=list(labels))


def replicate_rsd(X: np.ndarray, groups: Sequence[str], feature_names: Sequence[str]) -> pd.DataFrame:
    """RSD (%) tiap fitur di dalam tiap kelompok ulangan (minimal 2 anggota); NaN bila rata-rata nol."""
    X = np.asarray(X, dtype=float)
    groups = np.asarray(groups)
    columns: Dict[str, np.ndarray] = {}
    for group in sorted(set(groups)):
        block = X[groups == group]
        if block.shape[0] < 2:
            continue
        mean = block.mean(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            columns[str(group)] = np.where(mean > 0, 100.0 * block.std(axis=0, ddof=1) / mean, np.nan)
    return pd.DataFrame(columns, index=list(feature_names))


def hotelling_t2(scores: np.ndarray, labels: Sequence[str], alpha: float = 0.05) -> pd.DataFrame:
    """T2 Hotelling tiap sampel pada ruang skor PCA, batas kepercayaan (1 - alpha), dan penanda pencilan.

    Batas untuk pengamatan set latih: (n - 1)^2 / n * Beta(a/2, (n - a - 1)/2). NaN bila sampel terlalu sedikit.
    """
    scores = np.asarray(scores, dtype=float)
    n, a = scores.shape
    variance = np.where(scores.var(axis=0, ddof=1) > 0, scores.var(axis=0, ddof=1), np.nan) if n > 1 else np.full(a, np.nan)
    t2 = np.nansum(scores ** 2 / variance, axis=1)
    limit = ((n - 1) ** 2 / n) * sps.beta.ppf(1 - alpha, a / 2.0, (n - a - 1) / 2.0) if n - a - 1 > 0 else float("nan")
    return pd.DataFrame({"sample": list(labels), "t2": t2, "limit_95": limit,
                         "outlier": (t2 > limit) if np.isfinite(limit) else False})
