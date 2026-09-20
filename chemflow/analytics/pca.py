"""
PCA kemometrik berkelompok untuk membandingkan kelompok sampel (mis. senyawa
dari sumber berbeda, ligan uji terhadap native, atau sampel GC-MS asli terhadap
tiruan) berdasarkan matriks fitur numerik.

Gaya grafik mengikuti praktik jurnal kemometrik (mis. Aghoutane et al. 2023,
Micromachines 14:524, Gambar 5): tiap sampel adalah satu titik, warna
menandai seri (mis. jenis parfum) dan bentuk penanda menandai kelas (mis. asli
atau tiruan), elips kepercayaan 95% dilingkarkan per kelas, grid putus-putus,
dan sumbu diberi persentase variansi dua desimal.

PCA butuh minimal 2 kelas agar bermakna sebagai perbandingan. Bila hanya ada
satu kelas, ``compute()`` melempar ``ValueError`` yang jelas, bukan diam-diam
membuat plot yang tidak informatif.

``compute()`` menghitung sampai 3 komponen (dibatasi otomatis oleh jumlah
fitur dan sampel), ``plot_2d()`` memakai komponen 1 dan 2, ``plot_3d()`` memakai
komponen 1 sampai 3.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse

from chemflow.analytics.style import (
    FIG_DPI, annotate_without_overlap, chart_style, group_colors, save_figure,
)

CLASS_MARKERS = ["o", "v", "s", "^", "D", "P", "X", "h"]
ELLIPSE_LINESTYLES = ["-", "--", ":", "-."]
CHI2_95_2DOF = 5.991
SCALING_METHODS = ("auto", "pareto", "center")
_LOADING_LIMIT = 12   # jumlah fitur maksimum agar vektor loading digambar (di atasnya terlalu padat)
_LABEL_LIMIT = 40


@dataclass
class PcaResult:
    """Hasil transformasi PCA (2 atau 3 komponen, lihat ``n_components``)."""
    scores: np.ndarray              # (n_sampel, n_komponen)
    explained_variance_ratio: Tuple[float, ...]
    loadings: np.ndarray            # (n_fitur, n_komponen)
    feature_names: List[str]
    labels: List[str]
    groups: List[str]
    series: List[str] = field(default_factory=list)   # penanda warna; kosong = memakai groups
    scaling: str = "auto"
    axis_prefix: str = "PC"                           # awalan label sumbu ("LV" untuk skor PLS-DA)

    @property
    def n_components(self) -> int:
        return self.scores.shape[1]

    @property
    def color_keys(self) -> List[str]:
        return self.series if self.series else self.groups


def scale_matrix(X: np.ndarray, method: str = "auto") -> np.ndarray:
    """Pusatkan kolom, lalu skalakan: ``auto`` (z-score), ``pareto`` (bagi akar simpangan baku), atau ``center``."""
    if method not in SCALING_METHODS:
        raise ValueError(f"Metode penskalaan harus salah satu dari {SCALING_METHODS}, dapat: {method!r}")
    centered = X - X.mean(axis=0)
    if method == "center":
        return centered
    std = X.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    return centered / std if method == "auto" else centered / np.sqrt(std)


def confidence_ellipse(points: np.ndarray, chi2: float = CHI2_95_2DOF):
    """Pusat, lebar, tinggi, dan sudut (derajat) elips kepercayaan dari sebaran titik 2D; None bila tak terdefinisi."""
    if len(points) < 3:
        return None
    covariance = np.cov(points, rowvar=False)
    if not np.all(np.isfinite(covariance)):
        return None
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.clip(eigenvalues, 0, None)
    angle = float(np.degrees(np.arctan2(eigenvectors[1, 1], eigenvectors[0, 1])))
    width, height = 2 * np.sqrt(chi2 * eigenvalues[::-1])
    return points.mean(axis=0), float(width), float(height), angle


def confidence_ring_3d(points: np.ndarray, chi2: float = CHI2_95_2DOF, n: int = 100) -> Optional[np.ndarray]:
    """Cincin elips kepercayaan pada bidang dua sumbu utama sebaran titik 3D; None bila kurang dari 3 titik."""
    if len(points) < 3:
        return None
    covariance = np.cov(points, rowvar=False)
    if not np.all(np.isfinite(covariance)):
        return None
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.clip(eigenvalues, 0, None)
    major, minor = eigenvectors[:, 2], eigenvectors[:, 1]
    theta = np.linspace(0, 2 * np.pi, n)
    a, b = np.sqrt(chi2 * eigenvalues[2]), np.sqrt(chi2 * eigenvalues[1])
    return points.mean(axis=0) + np.outer(np.cos(theta), a * major) + np.outer(np.sin(theta), b * minor)


class ChemometricPCA:
    """PCA kemometrik dengan pengelompokan sampel berdasar kelas dan seri."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger(__name__)

    def compute(
        self,
        feature_matrix: List[List[float]],
        feature_names: List[str],
        labels: List[str],
        groups: List[str],
        n_components: int = 3,
        series: Optional[List[str]] = None,
        scaling: str = "auto",
    ) -> PcaResult:
        """Hitung PCA dari matriks fitur.

        Args:
            feature_matrix: matriks (n_sampel x n_fitur).
            feature_names: nama tiap kolom fitur (untuk loading).
            labels: nama sampel (untuk anotasi).
            groups: kelas tiap sampel (penanda dan elips), sama panjang dengan labels.
            n_components: 2 atau 3; diturunkan otomatis bila fitur atau sampel tak cukup.
            series: seri tiap sampel (warna), opsional. Tanpa seri, warna mengikuti kelas.
            scaling: ``auto`` (z-score, bawaan), ``pareto``, atau ``center``.

        Raises:
            ValueError: n_components di luar {2, 3}, kurang dari 2 kelas, kurang dari
                3 sampel, kurang dari 2 fitur, atau panjang argumen tidak sama.
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
        if len(labels) != X.shape[0] or len(groups) != X.shape[0] or (series and len(series) != X.shape[0]):
            raise ValueError("Panjang labels, groups, dan series harus sama dengan jumlah baris matriks.")

        actual_components = min(n_components, X.shape[1], X.shape[0] - 1)
        if actual_components < n_components:
            self._log.info(
                f"Komponen PCA diturunkan dari {n_components} ke {actual_components} "
                f"karena jumlah fitur/senyawa terbatas."
            )

        X_scaled = scale_matrix(X, scaling)
        try:
            scores, evr, loadings = self._pca_sklearn(X_scaled, actual_components)
        except ImportError:
            self._log.info("scikit-learn tidak terpasang, memakai fallback PCA numpy (eigh).")
            scores, evr, loadings = self._pca_numpy(X_scaled, actual_components)

        return PcaResult(
            scores=scores, explained_variance_ratio=evr, loadings=loadings, feature_names=feature_names,
            labels=labels, groups=groups, series=list(series) if series else [], scaling=scaling,
        )

    def plot_2d(self, result: PcaResult, output_path: "str | Path", title: str = "PCA Kemometrik (2D)",
                dpi: int = FIG_DPI, formats: Sequence[str] = ("png",),
                show_loadings: Optional[bool] = None, annotate: Optional[bool] = None) -> Path:
        """Plot PCA 2D (komponen 1 dan 2) bergaya jurnal.

        Warna menandai seri (atau kelas bila tanpa seri), bentuk penanda menandai
        kelas, dan elips kepercayaan 95% dilingkarkan per kelas (minimal 3 titik).
        Vektor loading digambar bila fitur tidak lebih dari 12 (atau dipaksa lewat
        ``show_loadings``); label titik ditulis bila sampel tidak lebih dari 40 dan
        tanpa seri (satu titik per sampel).
        """
        groups = sorted(set(result.groups))
        colors = group_colors(sorted(set(result.color_keys)))
        markers = {g: CLASS_MARKERS[i % len(CLASS_MARKERS)] for i, g in enumerate(groups)}
        ellipse_styles = self._ellipse_styles(result, groups, colors)
        if show_loadings is None:
            show_loadings = len(result.feature_names) <= _LOADING_LIMIT
        if annotate is None:
            annotate = not result.series and len(result.labels) <= _LABEL_LIMIT

        with chart_style():
            fig, ax = plt.subplots(figsize=(8.6, 6.4))
            for key, group in self._combinations(result):
                idx = [i for i, (k, g) in enumerate(zip(result.color_keys, result.groups)) if k == key and g == group]
                points = result.scores[idx, :2]
                ax.scatter(points[:, 0], points[:, 1], label=self._legend_label(result, key, group),
                           color=colors[key], marker=markers[group], s=78, edgecolors="black",
                           linewidths=0.7, zorder=3)
            drawn = []
            for group in groups:
                idx = [i for i, g in enumerate(result.groups) if g == group]
                ellipse = confidence_ellipse(result.scores[idx, :2])
                if ellipse is not None:
                    center, width, height, angle = ellipse
                    color, linestyle = ellipse_styles[group]
                    ax.add_patch(Ellipse(center, width, height, angle=angle, fill=False, edgecolor=color,
                                         linestyle=linestyle, linewidth=2.2, zorder=2))
                    drawn.append(group)

            loading_labels = []
            if show_loadings:
                scale = np.abs(result.scores[:, :2]).max() * 0.8 if result.scores.size else 1.0
                for i, feature in enumerate(result.feature_names):
                    x, y = result.loadings[i, 0] * scale, result.loadings[i, 1] * scale
                    ax.annotate("", xy=(x, y), xytext=(0, 0),
                                arrowprops=dict(arrowstyle="->", color="#777777", alpha=0.8, linewidth=1.0), zorder=2)
                    loading_labels.append(
                        ax.text(x * 1.08, y * 1.08, feature, fontsize=7.5, color="#555555", ha="center", va="center")
                    )

            self._style_axes(ax)
            ax.margins(0.08)
            ax.set_xlabel(self._axis_label(result, 0), fontweight="bold")
            ax.set_ylabel(self._axis_label(result, 1), fontweight="bold")
            ax.set_title(title)
            handles, labels = ax.get_legend_handles_labels()
            if result.series:
                for group in drawn:
                    color, linestyle = ellipse_styles[group]
                    handles.append(Line2D([0], [0], color=color, linestyle=linestyle, linewidth=2.2))
                    labels.append(f"Elips 95%: {group}")
            ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=True, edgecolor="black",
                      fontsize=9, title="Sampel" if result.series else "Kelompok")
            if annotate:
                annotate_without_overlap(ax, result.scores[:, 0], result.scores[:, 1], result.labels,
                                         fontsize=7.5, obstacles=loading_labels)
            return save_figure(fig, output_path, dpi=dpi, formats=formats)

    def plot_3d(self, result: PcaResult, output_path: "str | Path", title: str = "PCA Kemometrik (3D)",
                dpi: int = FIG_DPI, formats: Sequence[str] = ("png",),
                annotate: Optional[bool] = None) -> Optional[Path]:
        """Plot PCA 3D (komponen 1 sampai 3) bergaya jurnal, dengan cincin elips kepercayaan per kelas.

        Returns:
            Path PNG, atau ``None`` jika ``result`` hanya punya 2 komponen.
        """
        if result.n_components < 3:
            self._log.info("Plot PCA 3D dilewati: hasil compute() hanya punya 2 komponen.")
            return None

        groups = sorted(set(result.groups))
        colors = group_colors(sorted(set(result.color_keys)))
        markers = {g: CLASS_MARKERS[i % len(CLASS_MARKERS)] for i, g in enumerate(groups)}
        ellipse_styles = self._ellipse_styles(result, groups, colors)
        if annotate is None:
            annotate = not result.series and len(result.labels) <= 20

        with chart_style():
            fig = plt.figure(figsize=(8.6, 6.6))
            ax = fig.add_subplot(111, projection="3d")
            for key, group in self._combinations(result):
                idx = [i for i, (k, g) in enumerate(zip(result.color_keys, result.groups)) if k == key and g == group]
                ax.scatter(result.scores[idx, 0], result.scores[idx, 1], result.scores[idx, 2],
                           label=self._legend_label(result, key, group), color=colors[key], marker=markers[group],
                           s=64, edgecolors="black", linewidths=0.6, depthshade=False)
            drawn = []
            for group in groups:
                idx = [i for i, g in enumerate(result.groups) if g == group]
                ring = confidence_ring_3d(result.scores[idx, :3])
                if ring is not None:
                    color, linestyle = ellipse_styles[group]
                    ax.plot(ring[:, 0], ring[:, 1], ring[:, 2], color=color, linestyle=linestyle, linewidth=2.2)
                    drawn.append(group)
            if annotate:
                for label, (x, y, z) in zip(result.labels, result.scores[:, :3]):
                    ax.text(x, y, z, f" {label}", fontsize=7.5)

            for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
                try:
                    axis._axinfo["grid"].update({"linestyle": "--", "linewidth": 0.6, "color": "#888888"})
                except (AttributeError, KeyError):
                    pass
            ax.view_init(elev=22, azim=-58)
            ax.set_xlabel(self._axis_label(result, 0), labelpad=10, fontweight="bold")
            ax.set_ylabel(self._axis_label(result, 1), labelpad=10, fontweight="bold")
            ax.set_zlabel(self._axis_label(result, 2), labelpad=8, fontweight="bold")
            ax.set_title(title)
            handles, labels = ax.get_legend_handles_labels()
            if result.series:
                for group in drawn:
                    color, linestyle = ellipse_styles[group]
                    handles.append(Line2D([0], [0], color=color, linestyle=linestyle, linewidth=2.2))
                    labels.append(f"Elips 95%: {group}")
            ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.2, 0.5), frameon=True, edgecolor="black",
                      fontsize=9, title="Sampel" if result.series else "Kelompok")
            return save_figure(fig, output_path, dpi=dpi, formats=formats)

    @staticmethod
    def _ellipse_styles(result: PcaResult, groups: List[str], colors) -> dict:
        """Warna dan gaya garis elips per kelas.

        Tanpa seri, warna kelas dipakai (sewarna penanda). Dengan seri, warna sudah menandai seri, jadi
        elips memakai abu-abu tua dan dibedakan lewat gaya garis agar tidak dikira seri.
        """
        if result.series:
            return {g: ("#333333", ELLIPSE_LINESTYLES[i % len(ELLIPSE_LINESTYLES)]) for i, g in enumerate(groups)}
        return {g: (colors[g], "-") for g in groups}

    @staticmethod
    def _combinations(result: PcaResult) -> List[Tuple[str, str]]:
        """Pasangan (warna, kelas) yang ada di data, urut abjad."""
        return sorted(set(zip(result.color_keys, result.groups)))

    @staticmethod
    def _legend_label(result: PcaResult, key: str, group: str) -> str:
        return f"{key} ({group})" if result.series else group

    @staticmethod
    def _axis_label(result: PcaResult, index: int) -> str:
        return f"{result.axis_prefix}{index + 1} ({result.explained_variance_ratio[index] * 100:.2f} %)"

    @staticmethod
    def _style_axes(ax) -> None:
        ax.grid(True, linestyle="--", linewidth=0.6, color="#999999", zorder=0)
        ax.axhline(0, color="#BBBBBB", linewidth=0.8, zorder=1)
        ax.axvline(0, color="#BBBBBB", linewidth=0.8, zorder=1)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("black")
            spine.set_linewidth(1.0)

    @staticmethod
    def _standardize(X: np.ndarray) -> np.ndarray:
        return scale_matrix(X, "auto")

    @staticmethod
    def _pca_sklearn(X_scaled: np.ndarray, n_components: int) -> Tuple[np.ndarray, Tuple[float, ...], np.ndarray]:
        from sklearn.decomposition import PCA

        pca = PCA(n_components=n_components)
        scores = pca.fit_transform(X_scaled)
        return scores, tuple(pca.explained_variance_ratio_[:n_components]), pca.components_.T

    @staticmethod
    def _pca_numpy(X_scaled: np.ndarray, n_components: int) -> Tuple[np.ndarray, Tuple[float, ...], np.ndarray]:
        """Cadangan bila scikit-learn tidak ada: eigendekomposisi matriks kovarians."""
        cov = np.cov(X_scaled, rowvar=False)
        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        eigvals, eigvecs = eigvals[order], eigvecs[:, order]
        top = eigvecs[:, :n_components]
        total = eigvals.sum()
        evr = tuple((eigvals[:n_components] / total).tolist()) if total > 0 else tuple(0.0 for _ in range(n_components))
        return X_scaled @ top, evr, top
