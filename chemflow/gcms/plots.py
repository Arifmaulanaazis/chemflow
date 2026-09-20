"""Grafik analisis GC-MS: kromatogram, penyelarasan, kemiripan, statistik, dan skrining alergen."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, leaves_list, linkage

from chemflow.analytics.style import (
    CMAP_DIVERGING, FIG_DPI, annotate_without_overlap, chart_style, clean_axes, group_colors, save_figure, text_color_for,
)
from chemflow.gcms.models import Peak
from chemflow.gcms.stats import ClassificationResult

MAX_ANNOTATED_SAMPLES = 12


class GcmsPlotter:
    """Pembuat grafik GC-MS; tiap metode menulis satu gambar dan mengembalikan path PNG-nya."""

    def __init__(self, dpi: int = FIG_DPI, formats: Sequence[str] = ("png",)) -> None:
        self.dpi = dpi
        self.formats = tuple(formats)

    def _save(self, fig, path: "str | Path") -> Path:
        return save_figure(fig, path, dpi=self.dpi, formats=self.formats)

    def chromatogram_overlay(self, grid: np.ndarray, signals: np.ndarray, names: Sequence[str],
                             keys: Sequence[str], path: "str | Path", title: str = "Kromatogram TIC",
                             stacked: Optional[bool] = None) -> Path:
        """Semua kromatogram pada satu sumbu waktu, diwarnai per seri; bertumpuk bila sampel sedikit."""
        stacked = len(names) <= 8 if stacked is None else stacked
        colors = group_colors(sorted(set(keys), key=list(keys).index))
        peak = float(signals.max()) or 1.0
        with chart_style():
            fig, ax = plt.subplots(figsize=(11, 3.2 + (0.7 * len(names) if stacked else 2.6)))
            for i, (name, y) in enumerate(zip(names, signals)):
                offset = i * 0.55 * peak if stacked else 0.0
                ax.plot(grid, y + offset, color=colors[keys[i]], linewidth=1.0, label=name)
                if stacked:
                    ax.text(grid[0], offset + 0.05 * peak, name, fontsize=8, color=colors[keys[i]], va="bottom")
            ax.set_xlabel("Waktu retensi (menit)")
            ax.set_title(title)
            ax.set_xlim(grid[0], grid[-1])
            if stacked:
                ax.set_yticks([])
                ax.set_ylabel("Intensitas (tiap sampel diberi offset)")
            else:
                ax.set_ylabel("Intensitas (satuan detektor)")
                ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
            if not stacked:
                ax.legend(loc="upper right", ncol=2 if len(names) > 6 else 1)
            clean_axes(ax, grid_axis="x")
            return self._save(fig, path)

    def annotated_chromatogram(self, grid: np.ndarray, raw: np.ndarray, baseline: np.ndarray, corrected: np.ndarray,
                               peaks: Sequence[Peak], name: str, path: "str | Path", top_n: int = 15) -> Path:
        """Satu sampel: sinyal mentah dengan baseline (atas) dan sinyal terkoreksi dengan puncak berlabel RT (bawah)."""
        with chart_style():
            fig, (top, bottom) = plt.subplots(2, 1, figsize=(11, 6.6), sharex=True, gridspec_kw={"height_ratios": [1, 1.6]})
            top.plot(grid, raw, color="#555555", linewidth=0.9, label="Sinyal mentah")
            top.plot(grid, baseline, color="#D55E00", linewidth=1.4, label="Baseline (ALS)")
            top.legend(loc="upper right")
            top.set_ylabel("Intensitas")
            top.set_title(f"{name}: baseline dan puncak terdeteksi ({len(peaks)} puncak)")
            bottom.plot(grid, corrected, color="#0072B2", linewidth=1.0)
            ranked = sorted(peaks, key=lambda p: p.height, reverse=True)[:top_n]
            bottom.scatter([p.rt for p in peaks], [p.height for p in peaks], s=10, color="#D55E00", zorder=3)
            ylim = float(corrected.max()) * 1.18
            bottom.set_ylim(0, ylim)
            bottom.set_xlim(grid[0], grid[-1])
            annotate_without_overlap(bottom, [p.rt for p in ranked], [p.height for p in ranked],
                                     [f"{p.rt:.2f}" for p in ranked], fontsize=7.5)
            bottom.set_xlabel("Waktu retensi (menit)")
            bottom.set_ylabel("Intensitas terkoreksi")
            for ax in (top, bottom):
                ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
                clean_axes(ax, grid_axis="x")
            return self._save(fig, path)

    def mirror_plot(self, grid: np.ndarray, first: np.ndarray, second: np.ndarray, label_first: str, label_second: str,
                    similarity: float, path: "str | Path") -> Path:
        """Kromatogram rata-rata dua kelompok berhadapan (atas dan cermin bawah), dinormalkan ke puncak terbesar."""
        scale = max(float(first.max()), float(second.max()), 1e-12)
        with chart_style():
            fig, ax = plt.subplots(figsize=(11, 5.2))
            ax.plot(grid, first / scale, color="#0072B2", linewidth=1.0)
            ax.fill_between(grid, 0, first / scale, color="#0072B2", alpha=0.25)
            ax.plot(grid, -second / scale, color="#D55E00", linewidth=1.0)
            ax.fill_between(grid, 0, -second / scale, color="#D55E00", alpha=0.25)
            ax.axhline(0, color="#444444", linewidth=0.8)
            ax.set_xlim(grid[0], grid[-1])
            ax.set_yticks([-1, -0.5, 0, 0.5, 1])
            ax.set_yticklabels(["1.0", "0.5", "0", "0.5", "1.0"])
            ax.text(0.01, 0.95, label_first, transform=ax.transAxes, color="#0072B2", fontweight="bold", va="top")
            ax.text(0.01, 0.05, label_second, transform=ax.transAxes, color="#D55E00", fontweight="bold", va="bottom")
            ax.set_xlabel("Waktu retensi (menit)")
            ax.set_ylabel("Intensitas relatif")
            ax.set_title(f"Perbandingan kromatogram: kemiripan kosinus {similarity:.3f}")
            clean_axes(ax, grid_axis="x")
            return self._save(fig, path)

    def alignment_check(self, grid: np.ndarray, before: np.ndarray, after: np.ndarray, shifts: np.ndarray,
                        names: Sequence[str], path: "str | Path") -> Path:
        """Pergeseran RT per sampel (kiri) dan tumpang tindih puncak terbesar sebelum dan sesudah selaras (kanan)."""
        center = self._sharpest_peak(grid, after.mean(axis=0))
        window = (grid > center - 0.4) & (grid < center + 0.4)
        with chart_style():
            fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), gridspec_kw={"width_ratios": [1, 1.3, 1.3]})
            axes[0].barh(range(len(names)), shifts * 60.0, color="#56B4E9", edgecolor="#333333")
            axes[0].set_yticks(range(len(names)))
            axes[0].set_yticklabels(names, fontsize=8)
            axes[0].set_xlabel("Pergeseran RT diterapkan (detik)")
            axes[0].set_title("Penyelarasan")
            for ax, data, label in ((axes[1], before, "Sebelum"), (axes[2], after, "Sesudah")):
                for y in data:
                    ax.plot(grid[window], y[window] / max(float(data[:, window].max()), 1e-12), linewidth=1.0)
                ax.set_title(f"{label} (sekitar {center:.2f} menit)")
                ax.set_xlabel("Waktu retensi (menit)")
            axes[1].set_ylabel("Intensitas relatif")
            for ax in axes:
                clean_axes(ax)
            fig.tight_layout()
            return self._save(fig, path)

    @staticmethod
    def _sharpest_peak(grid: np.ndarray, signal: np.ndarray) -> float:
        """RT puncak yang paling tajam (prominence terhadap lebar terbesar); puncak datar atau tersaturasi dihindari."""
        from scipy.signal import find_peaks, peak_widths

        peaks, props = find_peaks(signal, prominence=0.15 * float(signal.max()), width=1)
        if peaks.size == 0:
            return float(grid[int(np.argmax(signal))])
        widths = peak_widths(signal, peaks, rel_height=0.5)[0]
        return float(grid[peaks[int(np.argmax(props["prominences"] / np.maximum(widths, 1.0)))]])

    def scree_plot(self, explained: Sequence[float], path: "str | Path", title: str = "Variansi tiap komponen") -> Path:
        values = np.asarray(explained) * 100.0
        with chart_style():
            fig, ax = plt.subplots(figsize=(6.4, 4.4))
            ax.bar(range(1, len(values) + 1), values, color="#0072B2", edgecolor="#222222")
            ax.plot(range(1, len(values) + 1), np.cumsum(values), color="#D55E00", marker="o")
            for i, value in enumerate(values, start=1):
                ax.text(i, value + 1, f"{value:.1f}", ha="center", fontsize=8)
            ax.set_xticks(range(1, len(values) + 1))
            ax.set_xticklabels([f"PC{i}" for i in range(1, len(values) + 1)])
            ax.set_ylabel("Variansi dijelaskan (%)")
            ax.set_title(title)
            clean_axes(ax, grid_axis="y")
            return self._save(fig, path)

    def loadings_plot(self, rts: np.ndarray, loadings: np.ndarray, explained: Sequence[float], path: "str | Path",
                      top_n: int = 8) -> Path:
        """Loading PC1 dan PC2 terhadap RT fitur; fitur dengan |loading| terbesar diberi label RT."""
        with chart_style():
            fig, axes = plt.subplots(min(2, loadings.shape[1]), 1, figsize=(11, 6.4), sharex=True, squeeze=False)
            for c, ax in enumerate(axes[:, 0]):
                ax.vlines(rts, 0, loadings[:, c], color="#0072B2", linewidth=1.2)
                ax.axhline(0, color="#444444", linewidth=0.8)
                top = np.argsort(np.abs(loadings[:, c]))[::-1][:top_n]
                ax.scatter(rts[top], loadings[top, c], color="#D55E00", s=16, zorder=3)
                annotate_without_overlap(ax, rts[top], loadings[top, c], [f"{rts[i]:.2f}" for i in top], fontsize=7.5)
                ax.set_ylabel(f"Loading PC{c + 1} ({explained[c] * 100:.1f} %)")
                clean_axes(ax, grid_axis="x")
            axes[-1, 0].set_xlabel("Waktu retensi fitur (menit)")
            axes[0, 0].set_title("Loading PCA menurut waktu retensi")
            return self._save(fig, path)

    def clustered_heatmap(self, matrix: np.ndarray, sample_labels: Sequence[str], feature_labels: Sequence[str],
                          groups: Sequence[str], path: "str | Path", title: str = "Peta panas fitur teratas") -> Path:
        """Heatmap z-score fitur (kolom) per sampel (baris), baris diurutkan menurut klaster Ward dan diwarnai menurut kelompok."""
        std = matrix.std(axis=0)
        scaled = (matrix - matrix.mean(axis=0)) / np.where(std == 0, 1.0, std)
        order = leaves_list(linkage(scaled, "ward")) if scaled.shape[0] > 1 else np.arange(scaled.shape[0])
        col_order = leaves_list(linkage(scaled.T, "ward")) if scaled.shape[1] > 1 else np.arange(scaled.shape[1])
        colors = group_colors(sorted(set(groups), key=list(groups).index))
        with chart_style():
            width = max(9.0, 0.3 * scaled.shape[1] + 5.0)
            height = max(4.4, 0.42 * scaled.shape[0] + 3.4)
            fig = plt.figure(figsize=(width, height))
            bottom, top = 1.5 / height, 1.0 - 0.6 / height          # ruang untuk label fitur dan judul (inci)
            ax_dend = fig.add_axes([0.02, bottom, 0.1, top - bottom])
            ax_heat = fig.add_axes([0.13, bottom, 0.68, top - bottom])
            ax_bar = fig.add_axes([0.90, bottom, 0.015, top - bottom])
            if scaled.shape[0] > 1:
                dendrogram(linkage(scaled, "ward"), orientation="left", ax=ax_dend, no_labels=True,
                           color_threshold=0, above_threshold_color="#444444")
                ax_dend.invert_yaxis()
            ax_dend.axis("off")
            ordered = scaled[order][:, col_order]
            image = ax_heat.imshow(ordered, aspect="auto", cmap=CMAP_DIVERGING, vmin=-2.5, vmax=2.5)
            ax_heat.set_xticks(range(ordered.shape[1]))
            ax_heat.set_xticklabels([feature_labels[i] for i in col_order], rotation=90, fontsize=7)
            ax_heat.set_yticks(range(len(order)))
            ax_heat.set_yticklabels([sample_labels[i] for i in order], fontsize=8)
            ax_heat.yaxis.tick_right()
            for text, index in zip(ax_heat.get_yticklabels(), order):
                text.set_color(colors[groups[index]])
                text.set_fontweight("bold")
            fig.colorbar(image, cax=ax_bar, label="z-score")
            fig.suptitle(title, x=0.13, ha="left", y=1.0 - 0.15 / height)
            return self._save(fig, path)

    def similarity_heatmap(self, table: pd.DataFrame, path: "str | Path", title: str) -> Path:
        values = table.to_numpy()
        low = float(np.floor(min(values.min(), 0.9) * 20) / 20)
        with chart_style():
            size = max(4.6, 0.55 * len(table) + 2.4)
            fig, ax = plt.subplots(figsize=(size + 0.8, size))
            image = ax.imshow(values, cmap="viridis", vmin=low, vmax=1.0)
            ax.set_xticks(range(len(table)))
            ax.set_yticks(range(len(table)))
            ax.set_xticklabels(table.columns, rotation=60, ha="right", fontsize=8)
            ax.set_yticklabels(table.index, fontsize=8)
            if len(table) <= 12:
                for i in range(len(table)):
                    for j in range(len(table)):
                        ax.text(j, i, f"{values[i, j]:.2f}", ha="center", va="center", fontsize=7.5,
                                color=text_color_for(image.cmap(image.norm(values[i, j]))))
            fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Kemiripan")
            ax.set_title(title)
            return self._save(fig, path)

    def volcano(self, table: pd.DataFrame, classes: Sequence[str], path: "str | Path", q_limit: float = 0.05,
                fold_limit: float = 1.0, label_top: int = 10) -> Optional[Path]:
        """Volcano untuk dua kelas: log2 fold change terhadap -log10 q (Welch, koreksi BH)."""
        if not {"log2_fold_change", "q_welch"} <= set(table.columns) or table["q_welch"].notna().sum() == 0:
            return None
        data = table.dropna(subset=["log2_fold_change", "q_welch"])
        x, y = data["log2_fold_change"].to_numpy(), -np.log10(np.clip(data["q_welch"].to_numpy(), 1e-300, 1.0))
        significant = (data["q_welch"].to_numpy() < q_limit) & (np.abs(x) >= fold_limit)
        with chart_style():
            fig, ax = plt.subplots(figsize=(7.4, 5.6))
            ax.scatter(x[~significant], y[~significant], s=22, color="#999999", edgecolor="none", label="Tidak signifikan")
            ax.scatter(x[significant], y[significant], s=30, color="#D55E00", edgecolor="#222222", linewidth=0.5,
                       label=f"q < {q_limit:g} dan |log2FC| >= {fold_limit:g}")
            ax.axhline(-np.log10(q_limit), color="#444444", linestyle="--", linewidth=0.9)
            for boundary in (-fold_limit, fold_limit):
                ax.axvline(boundary, color="#444444", linestyle="--", linewidth=0.9)
            top = np.argsort(-y)[:label_top]
            annotate_without_overlap(ax, x[top], y[top], [str(data["feature"].iloc[i]) for i in top], fontsize=7.5)
            ax.set_xlabel(f"log2 fold change ({classes[1]} terhadap {classes[0]})")
            ax.set_ylabel("-log10 q (Benjamini-Hochberg)")
            ax.set_title("Volcano plot")
            ax.legend(loc="upper left")
            clean_axes(ax, grid_axis="both")
            return self._save(fig, path)

    def vip_plot(self, names: Sequence[str], vip: np.ndarray, favored: Sequence[str], path: "str | Path",
                 top_n: int = 20) -> Path:
        """VIP tertinggi; warna batang menunjukkan kelas dengan rata-rata fitur lebih tinggi."""
        order = np.argsort(vip)[::-1][:top_n][::-1]
        colors = group_colors(sorted(set(favored), key=list(favored).index))
        with chart_style():
            fig, ax = plt.subplots(figsize=(7.6, 0.32 * len(order) + 2.0))
            ax.barh(range(len(order)), vip[order], color=[colors[favored[i]] for i in order], edgecolor="#222222")
            ax.set_yticks(range(len(order)))
            ax.set_yticklabels([names[i] for i in order], fontsize=8)
            ax.axvline(1.0, color="#444444", linestyle="--", linewidth=0.9)
            ax.set_xlabel("VIP")
            ax.set_title("Penanda pembeda (VIP PLS-DA)")
            ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for c in colors.values()],
                      labels=[f"lebih tinggi pada {k}" for k in colors], loc="lower right")
            clean_axes(ax, grid_axis="x")
            return self._save(fig, path)

    def confusion_plot(self, result: ClassificationResult, path: "str | Path") -> Path:
        matrix = result.confusion.to_numpy()
        with chart_style():
            size = max(4.2, 0.9 * len(result.labels) + 2.4)
            fig, ax = plt.subplots(figsize=(size, size * 0.9))
            image = ax.imshow(matrix, cmap="Blues")
            ax.set_xticks(range(len(result.labels)))
            ax.set_yticks(range(len(result.labels)))
            ax.set_xticklabels(result.labels, rotation=45, ha="right")
            ax.set_yticklabels(result.labels)
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                            color=text_color_for(image.cmap(image.norm(matrix[i, j]))), fontweight="bold")
            ax.set_xlabel("Prediksi")
            ax.set_ylabel("Sebenarnya")
            ax.set_title(f"{result.method}: akurasi validasi silang {result.accuracy * 100:.1f} %")
            return self._save(fig, path)

    def permutation_plot(self, result: ClassificationResult, path: "str | Path") -> Optional[Path]:
        if result.permuted_accuracy.size == 0:
            return None
        with chart_style():
            fig, ax = plt.subplots(figsize=(6.4, 4.4))
            ax.hist(result.permuted_accuracy * 100.0, bins=20, color="#999999", edgecolor="#222222")
            ax.axvline(result.accuracy * 100.0, color="#D55E00", linewidth=2.0, label=f"Model asli ({result.accuracy * 100:.1f} %)")
            ax.set_xlabel("Akurasi validasi silang (%)")
            ax.set_ylabel("Jumlah permutasi")
            ax.set_title(f"Uji permutasi {result.method} (p = {result.permutation_p:.3f}, n = {result.n_permutations})")
            ax.legend(loc="upper left")
            clean_axes(ax, grid_axis="y")
            return self._save(fig, path)

    def peak_summary(self, names: Sequence[str], counts: Sequence[int], totals: Sequence[float], keys: Sequence[str],
                     path: "str | Path") -> Path:
        colors = group_colors(sorted(set(keys), key=list(keys).index))
        with chart_style():
            fig, axes = plt.subplots(1, 2, figsize=(11, 0.34 * len(names) + 2.4), sharey=True)
            positions = range(len(names))
            axes[0].barh(positions, counts, color=[colors[k] for k in keys], edgecolor="#222222")
            axes[1].barh(positions, totals, color=[colors[k] for k in keys], edgecolor="#222222")
            axes[0].set_yticks(list(positions))
            axes[0].set_yticklabels(names, fontsize=8)
            axes[0].invert_yaxis()
            axes[0].set_xlabel("Jumlah puncak terdeteksi")
            axes[1].set_xlabel("Total luas puncak")
            axes[1].ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
            axes[0].set_title("Ringkasan puncak per sampel", loc="left")
            for ax in axes:
                clean_axes(ax, grid_axis="x")
            return self._save(fig, path)

    def allergen_plot(self, table: pd.DataFrame, path: "str | Path") -> Path:
        """Alergen terdeteksi (baris) per sampel (kolom) sebagai persen luas puncak."""
        samples = list(table.columns)
        colors = group_colors(samples)
        with chart_style():
            fig, ax = plt.subplots(figsize=(8.4, 0.5 * len(table) * max(1, len(samples) * 0.45) + 2.4))
            height = 0.8 / len(samples)
            for k, sample in enumerate(samples):
                ax.barh(np.arange(len(table)) + k * height, table[sample].to_numpy(), height=height,
                        color=colors[sample], edgecolor="#222222", label=sample)
            ax.set_yticks(np.arange(len(table)) + 0.4 - height / 2)
            ax.set_yticklabels(table.index, fontsize=8)
            ax.invert_yaxis()
            ax.set_xlabel("Luas puncak relatif (%)")
            ax.set_title("Alergen wewangian terdeteksi (dugaan)")
            ax.legend(loc="lower right")
            clean_axes(ax, grid_axis="x")
            return self._save(fig, path)
