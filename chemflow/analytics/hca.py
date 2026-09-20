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

from chemflow.analytics.paging import paged_name, paginate
from chemflow.analytics.style import DEFAULT_MAX_ROWS, FIG_DPI, chart_style, clean_axes, group_colors, save_figure


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
        max_leaves: Optional[int] = DEFAULT_MAX_ROWS,
    ) -> List[Path]:
        """Dendrogram HCA dengan label daun diwarnai per kelompok sumber.

        Bila daun lebih banyak dari ``max_leaves``, dendrogram dipotong menjadi beberapa gambar.
        Tiap gambar adalah jendela daun dari dendrogram penuh yang sama (tinggi sumbu jarak
        sama), jadi garis yang melintas ke bagian lain terpotong tapi struktur klasternya utuh.

        Args:
            result: hasil ``compute()``.
            output_path: path PNG keluaran (bagian ke-n diberi akhiran ``_partNNofMM``).
            title: judul grafik.
            color_by_group: warnai label daun sesuai kelompok (butuh ``result.groups`` terisi).
            dpi: resolusi gambar.
            formats: format tambahan yang ditulis berdampingan (``svg``, ``pdf``).
            max_leaves: jumlah daun maksimum per gambar; ``None``/0 berarti tidak dipotong.

        Returns:
            Daftar path PNG yang ditulis.
        """
        output_path = Path(output_path)
        with chart_style():
            leaves = dendrogram(result.linkage_matrix, no_plot=True)["leaves"]
            ordered_labels = [result.labels[i] for i in leaves]

            color_map, group_by_label = {}, {}
            if color_by_group and result.groups:
                color_map = group_colors(sorted(set(result.groups)))
                group_by_label = dict(zip(result.labels, result.groups))

            paths: List[Path] = []
            for page in paginate(len(ordered_labels), max_leaves):
                fig, ax = plt.subplots(figsize=(max(7.5, 0.45 * page.count + 2), 5.8))
                dendrogram(
                    result.linkage_matrix, ax=ax, no_labels=True, color_threshold=0,
                    above_threshold_color="#444444",
                )
                # Daun ke-k berada di posisi 10k+5, jadi jendela [a, b) = [10a, 10b].
                ax.set_xlim(10 * page.start, 10 * page.stop)
                ax.set_xticks([10 * k + 5 for k in range(page.start, page.stop)])
                ticks = ax.set_xticklabels(page.slice(ordered_labels), rotation=60, ha="right",
                                           rotation_mode="anchor", fontsize=9)

                if color_map:
                    for tick_label in ticks:
                        group = group_by_label.get(tick_label.get_text())
                        if group is not None:
                            tick_label.set_color(color_map[group])
                            tick_label.set_fontweight("bold")
                    handles = [plt.Line2D([0], [0], marker="s", linestyle="", markersize=8,
                                          color=color_map[g], label=g) for g in color_map]
                    ax.legend(handles=handles, title="Kelompok", loc="upper right")

                ax.set_title(title + page.title_suffix)
                ax.set_ylabel("Jarak (Ward, Euclidean)")
                clean_axes(ax, grid_axis="y")
                paths.append(save_figure(fig, output_path.with_name(paged_name(output_path.name, page)),
                                         dpi=dpi, formats=formats))
            return paths

    @staticmethod
    def _standardize(X: np.ndarray) -> np.ndarray:
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std = np.where(std == 0, 1.0, std)
        return (X - mean) / std
