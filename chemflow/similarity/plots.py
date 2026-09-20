"""
Grafik hasil analisis similaritas interaksi.

- ``bar_similarity``: peringkat similaritas gabungan beserta komponen residu
  dan tipe interaksi.
- ``scatter_vs_deltag``: grafik dua dimensi selisih afinitas (ΔG uji dikurangi
  ΔG referensi) terhadap similaritas interaksi, seperti diusulkan Pratama et
  al. (2021); ligan terbaik berada di kiri atas.
- ``footprint_heatmaps``: heatmap terklaster jejak kontak residu (ligan x
  residu) per reseptor, termasuk baris ligan native sebagai acuan.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from chemflow.analytics.heatmap import HeatmapBuilder
from chemflow.analytics.paging import paged_name, paginate
from chemflow.analytics.style import (
    DEFAULT_MAX_COLS, DEFAULT_MAX_ROWS, FIG_DPI, MARKERS, PALETTE, annotate_without_overlap, chart_style,
    clean_axes, save_figure,
)
from chemflow.similarity.similarity import SimilarityResult


def _residue_number(label: str) -> int:
    try:
        return int(label.split("-")[0])
    except ValueError:
        return 0


class SimilarityPlotter:
    """Pembuat grafik untuk daftar ``SimilarityResult``."""

    def __init__(self, output_dir: "str | Path", dpi: int = FIG_DPI, formats: Sequence[str] = ("png",),
                 logger: Optional[logging.Logger] = None, max_rows: Optional[int] = DEFAULT_MAX_ROWS,
                 max_cols: Optional[int] = DEFAULT_MAX_COLS) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dpi = dpi
        self._formats = tuple(formats)
        self._log = logger or logging.getLogger(__name__)
        self._max_rows = max_rows
        self._max_cols = max_cols

    def plot_all(self, results: List[SimilarityResult]) -> List[Path]:
        """Buat seluruh grafik yang datanya tersedia; grafik tanpa data dilewati."""
        paths: List[Path] = []
        if not results:
            return paths
        paths.extend(self.bar_similarity(results))
        scatter = self.scatter_vs_deltag(results)
        if scatter is not None:
            paths.append(scatter)
        paths.extend(self.footprint_heatmaps(results))
        return paths

    def bar_similarity(self, results: List[SimilarityResult], filename: str = "similaritas_bar.png") -> List[Path]:
        """Bar horizontal similaritas per ligan, urut dari yang paling mirip dengan referensi.

        Dipotong menjadi beberapa bagian bila ligan lebih banyak dari ``max_rows``.
        """
        if not results:
            return []

        multi_receptor = len({r.receptor_key for r in results}) > 1
        ordered = sorted(results, key=lambda r: r.overall_similarity_pct, reverse=True)
        labels = [f"{r.ligand_name} ({r.receptor_key})" if multi_receptor else r.ligand_name for r in ordered]
        aa = np.array([r.aa_similarity_pct for r in ordered])
        types = np.array([r.type_similarity_pct for r in ordered])
        overall = np.array([r.overall_similarity_pct for r in ordered])

        paths: List[Path] = []
        for page in paginate(len(labels), self._max_rows):
            page_labels = page.slice(labels)
            page_aa, page_types, page_overall = page.slice(aa), page.slice(types), page.slice(overall)
            with chart_style():
                fig, ax = plt.subplots(figsize=(8.0, max(3.2, 0.5 * len(page_labels) + 1.8)))
                ypos = np.arange(len(page_labels))
                height = 0.36
                ax.barh(ypos - height / 2, page_aa, height=height, color=PALETTE[0], label="Kemiripan residu")
                ax.barh(ypos + height / 2, page_types, height=height, color=PALETTE[3],
                        label="Kemiripan tipe interaksi")
                ax.scatter(page_overall, ypos, marker="D", s=46, color="#111111", zorder=4,
                           label="Similaritas gabungan")
                for y, value in zip(ypos, page_overall):
                    ax.annotate(f"{value:.1f}", (value, y), xytext=(8, 0), textcoords="offset points",
                                va="center", fontsize=8, color="#111111")

                ax.set_yticks(ypos)
                ax.set_yticklabels(page_labels)
                ax.invert_yaxis()
                ax.set_xlim(0, 112)
                ax.set_xlabel("Similaritas terhadap ligan native (%)")
                ax.set_title("Similaritas Interaksi Ligan-Reseptor" + page.title_suffix)
                clean_axes(ax, grid_axis="x")
                ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)
                paths.append(self._save(fig, paged_name(filename, page)))
        return paths

    def scatter_vs_deltag(self, results: List[SimilarityResult],
                          filename: str = "similaritas_vs_deltag.png") -> Optional[Path]:
        """Selisih ΔG (sumbu x) terhadap similaritas interaksi (sumbu y).

        Returns:
            Path PNG, atau ``None`` jika tak ada ligan dengan selisih ΔG
            (afinitas docking uji atau redocking native tidak tersedia).
        """
        points = [r for r in results if r.delta_g is not None]
        if not points:
            self._log.info("Grafik similaritas vs delta G dilewati: afinitas docking/redocking native tidak tersedia.")
            return None

        receptors = sorted({r.receptor_key for r in points})
        color_of = {rec: PALETTE[i % len(PALETTE)] for i, rec in enumerate(receptors)}
        marker_of = {rec: MARKERS[i % len(MARKERS)] for i, rec in enumerate(receptors)}

        with chart_style():
            fig, ax = plt.subplots(figsize=(7.5, 6.0))
            ax.axvline(0, color="#999999", linestyle="--", linewidth=0.9, zorder=1)
            for receptor in receptors:
                subset = [r for r in points if r.receptor_key == receptor]
                ax.scatter([r.delta_g for r in subset], [r.overall_similarity_pct for r in subset],
                           s=70, color=color_of[receptor], marker=marker_of[receptor], edgecolors="white",
                           linewidths=0.8, label=receptor, zorder=3)

            xs = np.array([r.delta_g for r in points])
            pad = max(0.5, 0.12 * (xs.max() - xs.min()))
            ax.set_xlim(min(xs.min(), 0) - pad, max(xs.max(), 0) + pad)
            ax.set_ylim(-4, 106)
            annotate_without_overlap(ax, [r.delta_g for r in points], [r.overall_similarity_pct for r in points],
                                     [r.ligand_name for r in points])
            ax.set_xlabel("Selisih afinitas terhadap referensi, ΔG uji - ΔG referensi (kcal/mol)")
            ax.set_ylabel("Similaritas interaksi (%)")
            ax.set_title("Similaritas Interaksi vs Selisih ΔG")
            ax.text(0.015, 0.985, "Terbaik: kiri atas", transform=ax.transAxes, va="top",
                    fontsize=8.5, color="#666666", style="italic")
            clean_axes(ax, grid_axis="both")
            if len(receptors) > 1:
                ax.legend(title="Reseptor", loc="lower right")
            return self._save(fig, filename)

    def footprint_heatmaps(self, results: List[SimilarityResult]) -> List[Path]:
        """Heatmap terklaster jejak kontak residu per reseptor (baris = ligan, kolom = residu)."""
        by_receptor: Dict[str, List[SimilarityResult]] = {}
        for result in results:
            by_receptor.setdefault(result.receptor_key, []).append(result)

        builder = HeatmapBuilder(self._dir, dpi=self._dpi, formats=self._formats, logger=self._log,
                                 max_rows=self._max_rows, max_cols=self._max_cols)
        paths: List[Path] = []
        for receptor, group in by_receptor.items():
            residues = sorted({res for r in group for res in r.test_residues + r.reference_residues},
                              key=_residue_number)
            if not residues:
                continue

            reference = group[0]
            rows = [(f"{reference.reference_name} (native)", set(reference.reference_residues))]
            rows.extend((r.ligand_name, set(r.test_residues)) for r in group)
            matrix = np.array([[1.0 if res in present else 0.0 for res in residues] for _, present in rows])

            safe_receptor = re.sub(r"[^A-Za-z0-9_.-]+", "_", receptor)
            paths.extend(builder.heatmap_clustered(
                matrix, [name for name, _ in rows], residues,
                filename=f"similaritas_jejak_{safe_receptor}.png",
                title=f"Jejak Kontak Residu: {receptor}", cbar_label="Kontak residu",
                cmap=ListedColormap(["#F2F2F2", PALETTE[0]]), cbar_ticks=[0.25, 0.75],
                cbar_ticklabels=["Tidak", "Ya"], vmin=0.0, vmax=1.0,
            ))
        return paths

    def _save(self, fig, filename: str) -> Path:
        path = save_figure(fig, self._dir / filename, dpi=self._dpi, formats=self._formats)
        self._log.debug(f"Grafik similaritas tersimpan: {path.name}")
        return path
