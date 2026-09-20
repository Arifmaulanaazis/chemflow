"""
Pemrosesan sinyal kromatogram GC-MS: koreksi baseline, penghalusan, penyelarasan
waktu retensi, deteksi puncak, pengelompokan puncak antar sampel, dan pembentukan
matriks fitur (per puncak atau per bin waktu).

Koreksi baseline memakai asymmetric least squares (Eilers dan Boelens 2005),
penghalusan Savitzky-Golay, deteksi puncak berbasis prominence dengan ambang
sinyal terhadap derau (S/N), dan penyelarasan lewat korelasi silang dengan
pergeseran dibatasi.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse
from scipy.signal import find_peaks, peak_widths, savgol_filter
from scipy.sparse.linalg import spsolve

from chemflow.gcms.models import Chromatogram, Peak

NORMALIZATIONS = ("total", "max", "pqn", "none")
TRANSFORMS = ("none", "log", "sqrt")
_trapezoid = getattr(np, "trapezoid", None) or np.trapz


def baseline_als(y: np.ndarray, lam: float = 1e7, p: float = 0.001, iterations: int = 10) -> np.ndarray:
    """Garis dasar lewat asymmetric least squares; ``lam`` makin besar makin kaku, ``p`` kecil menekan puncak."""
    n = y.size
    if n < 5:
        return np.zeros(n)
    diff = sparse.diags([1.0, -2.0, 1.0], [0, -1, -2], shape=(n, n - 2))
    penalty = lam * diff.dot(diff.T)
    weights = np.ones(n)
    z = y
    for _ in range(iterations):
        system = (sparse.spdiags(weights, 0, n, n) + penalty).tocsc()
        z = spsolve(system, weights * y)
        weights = p * (y > z) + (1 - p) * (y < z)
    return np.asarray(z)


def smooth_signal(y: np.ndarray, window_points: int, polyorder: int = 3) -> np.ndarray:
    """Savitzky-Golay; jendela dijadikan ganjil dan dibatasi panjang sinyal. Terlalu pendek: dikembalikan apa adanya."""
    window = int(window_points) | 1
    window = min(window, (y.size // 2) * 2 - 1)
    if window <= polyorder + 1:
        return y.copy()
    return savgol_filter(y, window, polyorder)


def estimate_noise(y: np.ndarray) -> float:
    """Simpangan baku derau dari sisa penghalusan (median absolute deviation, skala normal)."""
    if y.size < 15:
        return 0.0
    residual = y - smooth_signal(y, 11, 2)
    return float(1.4826 * np.median(np.abs(residual - np.median(residual))))


def preprocess(rt: np.ndarray, y: np.ndarray, baseline: bool = True, smooth_minutes: float = 0.02,
               lam: float = 1e7) -> Tuple[np.ndarray, np.ndarray]:
    """(sinyal terkoreksi tak negatif, garis dasar). Penghalusan dilakukan setelah baseline dikurangkan."""
    step = float(np.median(np.diff(rt))) if rt.size > 1 else 1.0
    base = baseline_als(y, lam=lam) if baseline else np.zeros_like(y)
    corrected = smooth_signal(y - base, max(5, int(round(smooth_minutes / step)))) if smooth_minutes > 0 else y - base
    return np.clip(corrected, 0.0, None), base


def common_grid(chromatograms: Sequence[Chromatogram], rt_range: Optional[Tuple[float, float]] = None) -> np.ndarray:
    """Sumbu RT bersama: irisan rentang semua sampel (atau ``rt_range``) dengan selang median."""
    signals = [c for c in chromatograms if c.has_signal]
    if not signals:
        return np.empty(0)
    low = max(c.rt[0] for c in signals)
    high = min(c.rt[-1] for c in signals)
    if rt_range is not None:
        low, high = max(low, rt_range[0]), min(high, rt_range[1])
    if high <= low:
        raise ValueError("Rentang RT sampel tidak beririsan (atau di luar rt_range); periksa satuan RT tiap berkas.")
    step = float(np.median([c.scan_interval for c in signals]))
    return np.arange(low, high + step * 0.5, step)


def resample(chrom: Chromatogram, grid: np.ndarray) -> np.ndarray:
    return np.interp(grid, chrom.rt, chrom.intensity)


def _shift(signal: np.ndarray, lag: int) -> np.ndarray:
    """Geser isi sinyal ``lag`` titik ke kanan (lag positif), sisi yang kosong diisi nol."""
    if lag == 0:
        return signal
    out = np.zeros_like(signal)
    if lag > 0:
        out[lag:] = signal[:-lag]
    else:
        out[:lag] = signal[-lag:]
    return out


def _best_lag(reference: np.ndarray, signal: np.ndarray, max_lag: int) -> int:
    best, best_score = 0, -np.inf
    for lag in range(-max_lag, max_lag + 1):
        score = float(np.dot(reference, _shift(signal, lag)))
        if score > best_score:
            best, best_score = lag, score
    return best


def align_signals(grid: np.ndarray, matrix: np.ndarray, max_shift: float = 0.3,
                  iterations: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    """Selaraskan RT antar sampel (baris ``matrix``) lewat korelasi silang.

    Referensi awal adalah sampel yang paling mirip dengan yang lain (medoid), lalu
    rata-rata hasil penyelarasan. Kompresi akar dipakai agar puncak raksasa tidak
    mendominasi. Mengembalikan matriks selaras dan pergeseran (menit) tiap sampel.
    """
    n_samples = matrix.shape[0]
    shifts = np.zeros(n_samples)
    if n_samples < 2 or max_shift <= 0 or grid.size < 3:
        return matrix.copy(), shifts
    step = float(grid[1] - grid[0])
    max_lag = int(round(max_shift / step))
    compressed = np.sqrt(np.clip(matrix, 0.0, None))
    compressed = compressed / np.maximum(np.linalg.norm(compressed, axis=1, keepdims=True), 1e-12)

    lags = np.zeros(n_samples, dtype=int)
    similarity = compressed @ compressed.T
    reference = compressed[int(np.argmax(similarity.sum(axis=1)))]
    for _ in range(max(1, iterations)):
        for i in range(n_samples):
            lags[i] = _best_lag(reference, compressed[i], max_lag)
        lags -= int(np.round(np.median(lags)))
        aligned = np.array([_shift(compressed[i], lags[i]) for i in range(n_samples)])
        reference = aligned.mean(axis=0)
        reference /= max(np.linalg.norm(reference), 1e-12)
    result = np.array([_shift(matrix[i], lags[i]) for i in range(n_samples)])
    return result, lags * step


def detect_peaks(rt: np.ndarray, y: np.ndarray, min_snr: float = 5.0, min_prominence: float = 0.005,
                 min_width: float = 0.01) -> List[Peak]:
    """Puncak pada sinyal terkoreksi baseline.

    Args:
        rt: sumbu waktu (menit), selang seragam.
        y: sinyal terkoreksi dan sudah dihaluskan.
        min_snr: tinggi minimal terhadap derau.
        min_prominence: prominence minimal sebagai pecahan tinggi maksimum sinyal.
        min_width: lebar minimal puncak dalam menit (menyaring lonjakan satu titik).
    """
    if y.size < 5 or not np.any(y > 0):
        return []
    step = float(np.median(np.diff(rt)))
    noise = estimate_noise(y)
    threshold = max(min_snr * noise, min_prominence * float(y.max()), 1e-12)
    indices, props = find_peaks(y, prominence=threshold, width=max(1.0, min_width / step))
    if indices.size == 0:
        return []
    _, _, left_ips, right_ips = peak_widths(y, indices, rel_height=0.95)
    peaks: List[Peak] = []
    for k, apex in enumerate(indices):
        left = max(int(np.floor(left_ips[k])), int(props["left_bases"][k]))
        right = min(int(np.ceil(right_ips[k])), int(props["right_bases"][k]))
        peaks.append(Peak(
            rt=float(rt[apex]), height=float(y[apex]), area=float(_trapezoid(y[left:right + 1], rt[left:right + 1])),
            start=float(rt[left]), end=float(rt[right]), snr=float(y[apex] / noise) if noise > 0 else float("inf"),
        ))
    total = sum(p.area for p in peaks)
    for peak in peaks:
        peak.area_pct = 100.0 * peak.area / total if total > 0 else float("nan")
    return peaks


def cluster_peaks(peak_lists: Sequence[Sequence[Peak]], tolerance: float) -> List[List[Tuple[int, Peak]]]:
    """Kelompokkan puncak antar sampel menurut RT (satu puncak per sampel per kelompok).

    Puncak diurutkan menurut RT lalu dikumpulkan sampai selisih dengan puncak
    sebelumnya melebihi ``tolerance``, rentang kelompok melebihi dua kali
    ``tolerance``, atau sampel yang sama muncul lagi.
    """
    items = sorted(((p.rt, s, p) for s, peaks in enumerate(peak_lists) for p in peaks), key=lambda item: item[0])
    clusters: List[List[Tuple[int, Peak]]] = []
    current: List[Tuple[int, Peak]] = []
    members = set()
    for rt, sample, peak in items:
        if current and (rt - current[-1][1].rt > tolerance or rt - current[0][1].rt > 2 * tolerance or sample in members):
            clusters.append(current)
            current, members = [], set()
        current.append((sample, peak))
        members.add(sample)
    if current:
        clusters.append(current)
    return clusters


def peak_feature_matrix(grid: np.ndarray, corrected: np.ndarray, peak_lists: Sequence[Sequence[Peak]],
                        tolerance: float, min_presence: float = 0.0, fill_gaps: bool = True,
                        min_snr: float = 5.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """Matriks area (sampel x puncak selaras), tinggi, RT tiap fitur, dan nama (dari laporan instrumen, bila ada).

    ``min_presence`` adalah pecahan sampel minimal yang harus memiliki puncak itu.
    Sel kosong diisi dari sinyal pada jendela ``tolerance`` bila tingginya melewati
    ``min_snr`` kali derau sampel itu, dengan luas = tinggi x rasio luas/tinggi puncak
    yang ditemukan; selain itu nol.
    """
    n_samples = len(peak_lists)
    noise = np.array([estimate_noise(corrected[i]) for i in range(n_samples)])
    clusters = [c for c in cluster_peaks(peak_lists, tolerance) if len(c) / max(n_samples, 1) >= min_presence]
    areas = np.zeros((n_samples, len(clusters)))
    heights = np.zeros_like(areas)
    rts = np.zeros(len(clusters))
    names: List[str] = []
    for j, cluster in enumerate(clusters):
        rts[j] = float(np.median([p.rt for _, p in cluster]))
        present = {s for s, _ in cluster}
        for sample, peak in cluster:
            areas[sample, j], heights[sample, j] = peak.area, peak.height
        labels = [p.name for _, p in cluster if p.name]
        names.append(max(set(labels), key=labels.count) if labels else "")
        if fill_gaps and len(present) < n_samples:
            ratio = float(np.mean([p.area / p.height for _, p in cluster if p.height > 0] or [0.0]))
            window = (grid >= rts[j] - tolerance) & (grid <= rts[j] + tolerance)
            for sample in set(range(n_samples)) - present:
                height = float(corrected[sample, window].max()) if window.any() else 0.0
                if noise[sample] > 0 and height >= min_snr * noise[sample]:
                    heights[sample, j], areas[sample, j] = height, height * ratio
    return areas, heights, rts, names


def bin_matrix(grid: np.ndarray, corrected: np.ndarray, bin_width: float) -> Tuple[np.ndarray, np.ndarray]:
    """Integral sinyal per bin waktu (sidik jari kromatogram): (pusat bin, matriks sampel x bin)."""
    edges = np.arange(grid[0], grid[-1] + bin_width, bin_width)
    index = np.clip(np.digitize(grid, edges) - 1, 0, len(edges) - 2)
    step = float(grid[1] - grid[0])
    values = np.zeros((corrected.shape[0], len(edges) - 1))
    for i in range(corrected.shape[0]):
        values[i] = np.bincount(index, weights=corrected[i], minlength=len(edges) - 1)[:len(edges) - 1] * step
    return (edges[:-1] + edges[1:]) / 2.0, values


def normalize_rows(X: np.ndarray, method: str = "total") -> np.ndarray:
    """Normalisasi per sampel: ``total`` (jumlah 100), ``max`` (puncak terbesar 100), ``pqn`` (Dieterle 2006), atau ``none``."""
    if method not in NORMALIZATIONS:
        raise ValueError(f"Normalisasi harus salah satu dari {NORMALIZATIONS}, dapat: {method!r}")
    X = np.asarray(X, dtype=float)
    if method == "none":
        return X.copy()
    if method == "max":
        scale = X.max(axis=1, keepdims=True)
        return 100.0 * X / np.where(scale > 0, scale, 1.0)
    scale = X.sum(axis=1, keepdims=True)
    total = 100.0 * X / np.where(scale > 0, scale, 1.0)
    if method == "total":
        return total
    reference = np.median(total, axis=0)
    result = total.copy()
    for i in range(total.shape[0]):
        usable = (total[i] > 0) & (reference > 0)
        if usable.any():
            result[i] = total[i] / np.median(total[i][usable] / reference[usable])
    return result


def transform_values(X: np.ndarray, method: str = "none") -> np.ndarray:
    """Transformasi penstabil variansi: ``log`` (log10 dengan offset separuh nilai positif terkecil) atau ``sqrt``."""
    if method not in TRANSFORMS:
        raise ValueError(f"Transformasi harus salah satu dari {TRANSFORMS}, dapat: {method!r}")
    X = np.asarray(X, dtype=float)
    if method == "none":
        return X.copy()
    if method == "sqrt":
        return np.sqrt(np.clip(X, 0.0, None))
    positive = X[X > 0]
    offset = 0.5 * float(positive.min()) if positive.size else 1.0
    return np.log10(np.clip(X, 0.0, None) + offset)
