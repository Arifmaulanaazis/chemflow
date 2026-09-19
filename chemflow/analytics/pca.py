"""
PCA kemometrik berkelompok. Analisis similaritas antar kelompok senyawa
(mis. senyawa dari tanaman/sumber berbeda) berbasis deskriptor numerik
(fisikokimia/ADMET) atau matriks afinitas docking multi-reseptor.

PCA butuh MINIMAL 2 kelompok untuk bermakna sebagai analisis similaritas
antar-kelompok. Kalau semua senyawa berasal dari 1 kelompok saja, tidak
ada apa pun untuk dibandingkan, jadi fungsi ini raise ``ValueError`` yang
jelas alih-alih diam-diam menghasilkan plot yang tidak informatif.

Mendukung 2 dan 3 komponen sekaligus dari satu kali komputasi: ``compute()``
menghitung sampai 3 komponen (dibatasi otomatis oleh jumlah fitur/senyawa
yang tersedia), lalu ``plot_2d()`` memakai komponen 1-2 dan ``plot_3d()``
memakai komponen 1-3 (dilewati kalau hanya 2 komponen yang tersedia).

Dua jalur implementasi: ``scikit-learn`` (disarankan, lebih efisien &
teruji) dengan fallback numpy ``eigh`` manual jika scikit-learn tidak
terpasang, supaya dependency scikit-learn bersifat opsional-tapi-dianjurkan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse

from chemflow.analytics.style import (
    FIG_DPI, MARKERS, PALETTE, annotate_without_overlap, chart_style, clean_axes, save_figure,
)


@dataclass
class PcaResult:
    """Hasil transformasi PCA (2 atau 3 komponen, lihat ``n_components``)."""
    scores: np.ndarray              # (n_samples, n_components)
    explained_variance_ratio: Tuple[float, ...]
    loadings: np.ndarray            # (n_features, n_components)
    feature_names: List[str]
    labels: List[str]
    groups: List[str]

    @property
    def n_components(self) -> int:
        return self.scores.shape[1]


class ChemometricPCA:
    """PCA kemometrik dengan pengelompokan senyawa berdasar sumber/kolom grup."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger(__name__)

    def compute(
        self,
        feature_matrix: List[List[float]],
        feature_names: List[str],
        labels: List[str],
        groups: List[str],
        n_components: int = 3,
    ) -> PcaResult:
        """Hitung PCA dari matriks deskriptor ter-standarisasi.

        Args:
            feature_matrix: matriks (n_senyawa x n_fitur), mis. deskriptor
                fisikokimia/ADMET numerik per senyawa.
            feature_names: nama tiap kolom fitur (untuk loading vectors).
            labels: nama senyawa (untuk anotasi scatter).
            groups: label kelompok sumber per senyawa (SAMA panjang dgn labels).
            n_components: jumlah komponen yang diminta (2 atau 3). Otomatis
                diturunkan jika jumlah fitur/senyawa tidak cukup untuk 3
                komponen; ``plot_3d()`` akan dilewati pada kasus itu.

        Returns:
            ``PcaResult``.

        Raises:
            ValueError: n_components di luar {2, 3}, jumlah kelompok unik
                < 2, atau data tidak cukup (< 3 senyawa, atau matriks fitur kosong).
        """
        if n_components not in (2, 3):
            raise ValueError(f"n_components harus 2 atau 3, dapat: {n_components}")

        unique_groups = sorted(set(groups))
        if len(unique_groups) < 2:
            raise ValueError(
                f"PCA kemometrik butuh minimal 2 kelompok senyawa untuk analisis "
                f"similaritas, hanya {len(unique_groups)} kelompok terdeteksi "
                f"({unique_groups!r}). Tambahkan senyawa dari sumber/kelompok lain, "
                f"atau tandai kelompok lewat kolom 'group' (mode tidy) / gunakan "
                f"format wide multi-kolom di Excel ligan."
            )

        X = np.array(feature_matrix, dtype=float)
        if X.shape[0] < 3:
            raise ValueError(f"PCA butuh minimal 3 senyawa dengan data lengkap, hanya {X.shape[0]} tersedia.")
        if X.shape[1] < 2:
            raise ValueError(f"PCA butuh minimal 2 fitur numerik, hanya {X.shape[1]} tersedia.")

        actual_components = min(n_components, X.shape[1], X.shape[0] - 1)
        if actual_components < n_components:
            self._log.info(
                f"Komponen PCA diturunkan dari {n_components} ke {actual_components} "
                f"karena jumlah fitur/senyawa terbatas."
            )

        X_std = self._standardize(X)

        try:
            scores, evr, loadings = self._pca_sklearn(X_std, actual_components)
        except ImportError:
            self._log.info("scikit-learn tidak terpasang, memakai fallback PCA numpy (eigh).")
            scores, evr, loadings = self._pca_numpy(X_std, actual_components)

        return PcaResult(
            scores=scores, explained_variance_ratio=evr, loadings=loadings,
            feature_names=feature_names, labels=labels, groups=groups,
        )

    def plot_2d(self, result: PcaResult, output_path: "str | Path", title: str = "PCA Kemometrik (2D)",
                dpi: int = FIG_DPI, formats: Sequence[str] = ("png",)) -> Path:
        """Biplot PCA 2D: skor per kelompok (warna dan penanda berbeda), elips
        kepercayaan 95% per kelompok (bila anggota minimal 3), dan vektor loading.

        Memakai komponen 1-2 dari ``result`` (berlaku untuk hasil 2 maupun 3 komponen).

        Args:
            result: hasil ``compute()``.
            output_path: path PNG keluaran.
            title: judul grafik.
            dpi: resolusi gambar.
            formats: format tambahan yang ditulis berdampingan (``svg``, ``pdf``).

        Returns:
            Path PNG yang ditulis.
        """
        unique_groups = sorted(set(result.groups))
        color_map = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(unique_groups)}
        marker_map = {g: MARKERS[i % len(MARKERS)] for i, g in enumerate(unique_groups)}

        with chart_style():
            fig, ax = plt.subplots(figsize=(7.5, 6.5))
            for group in unique_groups:
                idx = [i for i, g in enumerate(result.groups) if g == group]
                points = result.scores[idx, :2]
                ax.scatter(points[:, 0], points[:, 1], label=group, color=color_map[group],
                           marker=marker_map[group], s=62, alpha=0.9, edgecolors="white", linewidths=0.8, zorder=3)
                if len(idx) >= 4:
                    self._draw_ellipse(ax, points, color_map[group])

            scale = np.abs(result.scores[:, :2]).max() * 0.8 if result.scores.size else 1.0
            loading_labels = []
            for i, feature in enumerate(result.feature_names):
                x, y = result.loadings[i, 0] * scale, result.loadings[i, 1] * scale
                ax.annotate("", xy=(x, y), xytext=(0, 0),
                            arrowprops=dict(arrowstyle="->", color="#777777", alpha=0.8, linewidth=1.0), zorder=2)
                loading_labels.append(
                    ax.text(x * 1.08, y * 1.08, feature, fontsize=7.5, color="#555555", ha="center", va="center")
                )

            ax.set_xlabel(f"PC1 ({result.explained_variance_ratio[0] * 100:.1f}% variansi)")
            ax.set_ylabel(f"PC2 ({result.explained_variance_ratio[1] * 100:.1f}% variansi)")
            ax.set_title(title)
            ax.axhline(0, color="#CCCCCC", linewidth=0.8, zorder=1)
            ax.axvline(0, color="#CCCCCC", linewidth=0.8, zorder=1)
            clean_axes(ax)
            ax.legend(title="Kelompok", loc="best")
            if len(result.labels) <= 40:
                annotate_without_overlap(ax, result.scores[:, 0], result.scores[:, 1], result.labels,
                                         fontsize=7.5, obstacles=loading_labels)
            return save_figure(fig, output_path, dpi=dpi, formats=formats)

    def plot_3d(self, result: PcaResult, output_path: "str | Path", title: str = "PCA Kemometrik (3D)",
                dpi: int = FIG_DPI, formats: Sequence[str] = ("png",)) -> Optional[Path]:
        """Scatter PCA 3D berwarna per kelompok.

        Args:
            result: hasil ``compute()`` (harus punya 3 komponen).
            output_path: path PNG keluaran.
            title: judul grafik.
            dpi: resolusi gambar.
            formats: format tambahan yang ditulis berdampingan.

        Returns:
            Path PNG, atau ``None`` jika ``result`` hanya punya 2 komponen.
        """
        if result.n_components < 3:
            self._log.info("Plot PCA 3D dilewati: hasil compute() hanya punya 2 komponen.")
            return None

        unique_groups = sorted(set(result.groups))
        color_map = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(unique_groups)}
        marker_map = {g: MARKERS[i % len(MARKERS)] for i, g in enumerate(unique_groups)}

        with chart_style():
            fig = plt.figure(figsize=(7.5, 6.5))
            ax = fig.add_subplot(111, projection="3d")
            for group in unique_groups:
                idx = [i for i, g in enumerate(result.groups) if g == group]
                ax.scatter(result.scores[idx, 0], result.scores[idx, 1], result.scores[idx, 2],
                           label=group, color=color_map[group], marker=marker_map[group], s=52, alpha=0.9,
                           edgecolors="white", linewidths=0.6, depthshade=False)

            ax.set_xlabel(f"PC1 ({result.explained_variance_ratio[0] * 100:.1f}%)", labelpad=8)
            ax.set_ylabel(f"PC2 ({result.explained_variance_ratio[1] * 100:.1f}%)", labelpad=8)
            ax.set_zlabel(f"PC3 ({result.explained_variance_ratio[2] * 100:.1f}%)", labelpad=8)
            ax.set_title(title)
            ax.legend(title="Kelompok", loc="upper left")
            return save_figure(fig, output_path, dpi=dpi, formats=formats)

    @staticmethod
    def _draw_ellipse(ax, points: np.ndarray, color: str) -> None:
        """Elips kepercayaan 95% (chi-kuadrat 2 derajat bebas) untuk sebaran satu kelompok."""
        covariance = np.cov(points, rowvar=False)
        if not np.all(np.isfinite(covariance)):
            return
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        eigenvalues = np.clip(eigenvalues, 0, None)
        angle = np.degrees(np.arctan2(eigenvectors[1, 1], eigenvectors[0, 1]))
        width, height = 2 * np.sqrt(5.991 * eigenvalues[::-1])
        ax.add_patch(Ellipse(points.mean(axis=0), width, height, angle=angle, facecolor=color,
                             edgecolor=color, alpha=0.12, linewidth=1.0, zorder=2))

    @staticmethod
    def _standardize(X: np.ndarray) -> np.ndarray:
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std = np.where(std == 0, 1.0, std)
        return (X - mean) / std

    @staticmethod
    def _pca_sklearn(X_std: np.ndarray, n_components: int) -> Tuple[np.ndarray, Tuple[float, ...], np.ndarray]:
        from sklearn.decomposition import PCA

        pca = PCA(n_components=n_components)
        scores = pca.fit_transform(X_std)
        evr = tuple(pca.explained_variance_ratio_[:n_components])
        loadings = pca.components_.T  # (n_features, n_components)
        return scores, evr, loadings

    @staticmethod
    def _pca_numpy(X_std: np.ndarray, n_components: int) -> Tuple[np.ndarray, Tuple[float, ...], np.ndarray]:
        """Fallback PCA manual via eigendekomposisi matriks kovarians."""
        cov = np.cov(X_std, rowvar=False)
        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        eigvals, eigvecs = eigvals[order], eigvecs[:, order]

        top_vecs = eigvecs[:, :n_components]
        scores = X_std @ top_vecs
        total_var = eigvals.sum()
        evr = tuple((eigvals[:n_components] / total_var).tolist()) if total_var > 0 else tuple(0.0 for _ in range(n_components))
        return scores, evr, top_vecs
