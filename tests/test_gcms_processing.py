"""Test pemrosesan sinyal GC-MS: baseline, deteksi puncak, penyelarasan, pengelompokan, normalisasi."""

import numpy as np
import pytest

from chemflow.gcms import processing as proc
from chemflow.gcms.models import Chromatogram, Peak
from tests.gcms_data import COMMON_PEAKS, gaussian_area, make_trace, synthetic_peaks


def _corrected(peaks=None, **kwargs):
    rt, y = make_trace(peaks or synthetic_peaks(), **kwargs)
    corrected, base = proc.preprocess(rt, y)
    return rt, y, corrected, base


def test_baseline_mengikuti_drift_tanpa_menyerap_puncak():
    rt, y, corrected, base = _corrected(drift=5.0e4)
    drift = 1.0e3 + 5.0e4 * (rt - rt[0]) / (rt[-1] - rt[0])
    quiet = (rt > 5.2) & (rt < 5.8)
    assert np.mean(np.abs(base[quiet] - drift[quiet])) < 1500
    assert corrected.max() > 0.9 * max(h for _, h, _ in COMMON_PEAKS)
    assert corrected.min() >= 0.0


def test_baseline_pendek_dan_penghalusan_pendek_tidak_error():
    assert proc.baseline_als(np.ones(3)).tolist() == [0.0, 0.0, 0.0]
    assert proc.smooth_signal(np.arange(4.0), 11).tolist() == [0.0, 1.0, 2.0, 3.0]


def test_deteksi_puncak_menemukan_semua_puncak_sintetis():
    rt, _, corrected, _ = _corrected()
    peaks = proc.detect_peaks(rt, corrected)
    found = sorted(p.rt for p in peaks)
    assert len(peaks) == len(COMMON_PEAKS)
    assert found == pytest.approx(sorted(rt0 for rt0, _, _ in COMMON_PEAKS), abs=0.02)


def test_luas_puncak_mendekati_luas_gaussian_analitik():
    rt, _, corrected, _ = _corrected()
    for peak in proc.detect_peaks(rt, corrected):
        height, sigma = next((h, s) for r, h, s in COMMON_PEAKS if abs(r - peak.rt) < 0.03)
        assert peak.area == pytest.approx(gaussian_area(height, sigma), rel=0.06)
        assert peak.height == pytest.approx(height, rel=0.06)


def test_puncak_di_bawah_ambang_snr_dan_prominence_dibuang():
    kecil = synthetic_peaks(extra=[(10.0, 2000.0, 0.02)])
    rt, _, corrected, _ = _corrected(kecil, noise=300.0)
    bawaan = proc.detect_peaks(rt, corrected, min_snr=5.0, min_prominence=0.005)
    assert len(bawaan) == len(COMMON_PEAKS) and not any(abs(p.rt - 10.0) < 0.03 for p in bawaan)
    longgar = proc.detect_peaks(rt, corrected, min_snr=3.0, min_prominence=0.0005)
    assert any(abs(p.rt - 10.0) < 0.03 for p in longgar)


def test_persen_luas_berjumlah_100():
    rt, _, corrected, _ = _corrected()
    assert sum(p.area_pct for p in proc.detect_peaks(rt, corrected)) == pytest.approx(100.0)


def test_sinyal_datar_tidak_menghasilkan_puncak():
    assert proc.detect_peaks(np.linspace(0, 10, 500), np.zeros(500)) == []


def test_penyelarasan_memulihkan_pergeseran_rt():
    rt = make_trace(synthetic_peaks())[0]
    signals = np.array([proc.preprocess(rt, make_trace(synthetic_peaks(), jitter=j, seed=k)[1])[0]
                        for k, j in enumerate((0.0, 0.05, -0.04, 0.03))])
    aligned, shifts = proc.align_signals(rt, signals, max_shift=0.2)
    apex = [rt[np.argmax(row[(rt > 9.3) & (rt < 9.8)]) + np.argmax(rt > 9.3)] for row in aligned]
    assert max(apex) - min(apex) <= 0.011
    before = [rt[np.argmax(row[(rt > 9.3) & (rt < 9.8)]) + np.argmax(rt > 9.3)] for row in signals]
    assert max(before) - min(before) >= 0.08
    assert np.ptp(shifts) == pytest.approx(0.09, abs=0.015)


def test_penyelarasan_dibatasi_max_shift_dan_satu_sampel_dilewati():
    rt = make_trace(synthetic_peaks())[0]
    far = np.array([proc.preprocess(rt, make_trace(synthetic_peaks(), jitter=j, seed=k)[1])[0] for k, j in enumerate((0.0, 0.3))])
    _, shifts = proc.align_signals(rt, far, max_shift=0.05)
    assert np.abs(shifts).max() <= 0.051
    one = far[:1]
    out, zero = proc.align_signals(rt, one)
    assert np.array_equal(out, one) and zero.tolist() == [0.0]


def test_pengelompokan_puncak_satu_per_sampel_per_kelompok():
    lists = [[Peak(rt=5.00), Peak(rt=8.00)], [Peak(rt=5.02), Peak(rt=8.01)], [Peak(rt=5.03), Peak(rt=9.50)]]
    clusters = proc.cluster_peaks(lists, tolerance=0.05)
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2, 3]
    for cluster in clusters:
        assert len({s for s, _ in cluster}) == len(cluster)


def test_puncak_kembar_satu_sampel_dipisah_meski_berdekatan():
    clusters = proc.cluster_peaks([[Peak(rt=5.00), Peak(rt=5.03)], [Peak(rt=5.01)]], tolerance=0.05)
    assert all(len({s for s, _ in c}) == len(c) for c in clusters)


def test_matriks_fitur_puncak_dan_pengisian_celah():
    rt = make_trace(synthetic_peaks())[0]
    with_extra = synthetic_peaks(extra=[(16.0, 8.0e5, 0.025)])
    signals = np.array([proc.preprocess(rt, make_trace(with_extra, seed=1)[1])[0],
                        proc.preprocess(rt, make_trace(synthetic_peaks(extra=[(16.0, 9000.0, 0.025)]), seed=2)[1])[0],
                        proc.preprocess(rt, make_trace(synthetic_peaks(), seed=3)[1])[0]])
    peaks = [proc.detect_peaks(rt, row) for row in signals]
    areas, heights, rts, names = proc.peak_feature_matrix(rt, signals, peaks, 0.05, fill_gaps=False)
    j = int(np.argmin(np.abs(rts - 16.0)))
    assert areas[0, j] > 0 and areas[2, j] == 0
    filled, _, rts2, _ = proc.peak_feature_matrix(rt, signals, peaks, 0.05, fill_gaps=True)
    j2 = int(np.argmin(np.abs(rts2 - 16.0)))
    assert filled[1, j2] > 0 and filled[2, j2] == 0
    assert names == [""] * len(rts)


def test_kehadiran_minimal_menyaring_fitur():
    lists = [[Peak(rt=5.0, area=1.0, height=1.0)], [Peak(rt=5.0, area=1.0, height=1.0), Peak(rt=8.0, area=1.0, height=1.0)]]
    grid = np.linspace(4.0, 9.0, 500)
    signals = np.zeros((2, 500))
    areas, _, rts, _ = proc.peak_feature_matrix(grid, signals, lists, 0.05, min_presence=1.0, fill_gaps=False)
    assert rts.tolist() == [5.0] and areas.shape == (2, 1)


def test_nama_fitur_berasal_dari_nama_puncak_terbanyak():
    lists = [[Peak(rt=5.0, area=1.0, height=1.0, name="Linalool")], [Peak(rt=5.01, area=1.0, height=1.0, name="Linalool")],
             [Peak(rt=5.02, area=1.0, height=1.0, name="Lain")]]
    _, _, _, names = proc.peak_feature_matrix(np.linspace(4, 6, 200), np.zeros((3, 200)), lists, 0.05, fill_gaps=False)
    assert names == ["Linalool"]


def test_bin_menjaga_total_sinyal():
    rt, _, corrected, _ = _corrected()
    centers, bins = proc.bin_matrix(rt, corrected[None, :], 0.1)
    assert bins.sum() == pytest.approx(corrected.sum() * (rt[1] - rt[0]), rel=1e-6)
    assert centers[1] - centers[0] == pytest.approx(0.1)


def test_normalisasi_total_max_dan_tanpa():
    X = np.array([[1.0, 3.0], [10.0, 30.0]])
    assert proc.normalize_rows(X, "total").sum(axis=1).tolist() == pytest.approx([100.0, 100.0])
    assert proc.normalize_rows(X, "max").max(axis=1).tolist() == pytest.approx([100.0, 100.0])
    assert np.array_equal(proc.normalize_rows(X, "none"), X)
    assert proc.normalize_rows(np.zeros((2, 3)), "total").sum() == 0


def test_pqn_menghilangkan_faktor_pengenceran():
    rng = np.random.default_rng(0)
    base = rng.uniform(1, 10, 40)
    X = np.array([base, base * 2.0, base * 0.5])
    X[0, :4] *= 8.0                       # sebagian fitur berubah nyata, bukan pengenceran
    result = proc.normalize_rows(X, "pqn")
    ratio = np.median(result[1, 4:] / result[0, 4:])
    assert ratio == pytest.approx(1.0, rel=1e-6)


def test_normalisasi_tidak_dikenal_ditolak():
    with pytest.raises(ValueError, match="Normalisasi"):
        proc.normalize_rows(np.ones((2, 2)), "median")


def test_transformasi_log_sqrt_dan_nol_aman():
    X = np.array([[0.0, 1.0], [100.0, 10.0]])
    assert proc.transform_values(X, "none").tolist() == X.tolist()
    assert proc.transform_values(X, "sqrt").tolist() == [[0.0, 1.0], [10.0, np.sqrt(10.0)]]
    logged = proc.transform_values(X, "log")
    assert np.all(np.isfinite(logged)) and logged[1, 0] > logged[0, 1] > logged[0, 0]
    with pytest.raises(ValueError, match="Transformasi"):
        proc.transform_values(X, "cube")


def test_grid_bersama_dan_rentang_tidak_beririsan():
    a = Chromatogram("a", np.arange(5.0, 20.0, 0.01), np.ones(1500))
    b = Chromatogram("b", np.arange(6.0, 25.0, 0.01), np.ones(1900))
    grid = proc.common_grid([a, b])
    assert grid[0] == pytest.approx(6.0) and grid[-1] <= 20.0
    assert proc.common_grid([a, b], rt_range=(8.0, 12.0))[0] == pytest.approx(8.0)
    far = Chromatogram("c", np.arange(30.0, 40.0, 0.01), np.ones(1000))
    with pytest.raises(ValueError, match="tidak beririsan"):
        proc.common_grid([a, far])
