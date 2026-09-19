"""
Hierarchical Cluster Analysis (HCA) kemometrik: dendrogram pengelompokan
senyawa berbasis deskriptor numerik (fisikokimia/ADMET), sebagai pelengkap
PCA untuk melihat struktur kemiripan antar senyawa secara hierarkis.

Data distandarisasi (z-score) sebelum dihitung jarak Euclidean dan
linkage Ward, mengikuti konvensi umum kemometrik supaya fitur dengan
satuan/skala berbeda (mis. MW dalam Dalton vs probabilitas 0-1) tidak
mendominasi jarak hanya karena rentang nilainya lebih besar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage

from chemflow.analytics.style import FIG_DPI, PALETTE, chart_style, clean_axes, save_figure


@dataclass
class HcaResult:
    """Hasil linkage HCA, siap digambar sebagai dendrogram atau dipotong jadi klaster."""
    linkage_matrix: np.ndarray
    labels: List[str]
    groups: List[str] = field(default_factory=list)


class HierarchicalClustering:
    """HCA kemometrik dengan pewarnaan label daun dendrogram berdasar kelompok sumber."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger(__name__)

    def compute(
        self,
        feature_matrix: List[List[float]],
        labels: List[str],
        groups: Optional[List[str]] = None,
        method: str = "ward",
        metric: str = "euclidean",
    ) -> HcaResult:
        """Hitung linkage hierarkis dari matriks deskriptor ter-standarisasi.

        Args:
            feature_matrix: matriks (n_senyawa x n_fitur).
            labels: nama senyawa (jadi label daun dendrogram).
            groups: label kelompok sumber per senyawa, opsional (untuk
                pewarnaan label saat digambar). Panjang sama dengan labels.
            method: metode linkage scipy (default "ward", butuh metric="euclidean").
            metric: metrik jarak scipy (default "euclidean").

        Returns:
            ``HcaResult`` berisi matriks linkage.

        Raises:
            ValueError: kurang dari 2 senyawa atau matriks fitur kosong.
        """
        X = np.array(feature_matrix, dtype=float)
        if X.shape[0] < 2:
            raise ValueError(f"HCA butuh minimal 2 senyawa dengan data lengkap, hanya {X.shape[0]} tersedia.")
        if X.shape[1] < 1:
            raise ValueError("HCA butuh minimal 1 fitur numerik.")

        X_std = self._standardize(X)
        Z = linkage(X_std, method=method, metric=metric)

        return HcaResult(linkage_matrix=Z, labels=labels, groups=groups or [])

    def assign_clusters(self, result: HcaResult, n_clusters: int) -> Dict[str, int]:
        """Potong dendrogram menjadi ``n_clusters`` klaster diskrit.

        Args:
            result: hasil ``compute()``.
            n_clusters: jumlah klaster yang diinginkan.

        Returns:
            Pemetaan nama senyawa -> nomor klaster (1-based).
        """
        cluster_ids = fcluster(result.linkage_matrix, t=n_clusters, criterion="maxclust")
        return dict(zip(result.labels, (int(c) for c in cluster_ids)))

    def plot_dendrogram(
        self,
        result: HcaResult,
        output_path: "str | Path",
        title: str = "Dendrogram HCA",
        color_by_group: bool = True,
        dpi: int = FIG_DPI,
        formats: Sequence[str] = ("png",),
    ) -> Path:
        """Dendrogram HCA dengan label daun diwarnai per kelompok sumber.

        Args:
            result: hasil ``compute()``.
            output_path: path PNG keluaran.
            title: judul grafik.
            color_by_group: warnai label daun sesuai kelompok (butuh ``result.groups`` terisi).
            dpi: resolusi gambar.
            formats: format tambahan yang ditulis berdampingan (``svg``, ``pdf``).

        Returns:
            Path PNG yang ditulis.
        """
        with chart_style():
            fig, ax = plt.subplots(figsize=(max(7.5, 0.45 * len(result.labels) + 2), 5.8))
            dendrogram(
                result.linkage_matrix, labels=result.labels, ax=ax,
                leaf_rotation=60, leaf_font_size=9, color_threshold=0, above_threshold_color="#444444",
            )
            for label in ax.get_xticklabels():
                label.set_ha("right")
                label.set_rotation_mode("anchor")

            if color_by_group and result.groups:
                unique_groups = sorted(set(result.groups))
                color_map = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(unique_groups)}
                group_by_label = dict(zip(result.labels, result.groups))
                for tick_label in ax.get_xticklabels():
                    group = group_by_label.get(tick_label.get_text())
                    if group is not None:
                        tick_label.set_color(color_map[group])
                        tick_label.set_fontweight("bold")
                handles = [plt.Line2D([0], [0], marker="s", linestyle="", markersize=8,
                                      color=color_map[g], label=g) for g in unique_groups]
                ax.legend(handles=handles, title="Kelompok", loc="upper right")

            ax.set_title(title)
            ax.set_ylabel("Jarak (Ward, Euclidean)")
            clean_axes(ax, grid_axis="y")
            return save_figure(fig, output_path, dpi=dpi, formats=formats)

    @staticmethod
    def _standardize(X: np.ndarray) -> np.ndarray:
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std = np.where(std == 0, 1.0, std)
        return (X - mean) / std
