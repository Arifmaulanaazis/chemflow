"""
Heatmap matriks nilai untuk visualisasi hasil chemflow: afinitas docking
(reseptor x ligan) dan properti ADMET (ligan x parameter).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap

from chemflow.analytics.style import FIG_DPI, save_figure, styled


def format_cell_value(value: float) -> str:
    """Angka sel ringkas tanpa notasi ilmiah: 0 desimal untuk >= 100, 1 untuk >= 10, 2 untuk sisanya."""
    magnitude = abs(value)
    digits = 0 if magnitude >= 100 else 1 if magnitude >= 10 else 2
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


class HeatmapBuilder:
    """Pembuat heatmap untuk matriks reseptor x ligan atau ligan x properti."""

    def __init__(self, output_dir: "str | Path", dpi: int = FIG_DPI, formats: Sequence[str] = ("png",),
                 logger: Optional[logging.Logger] = None) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dpi = dpi
        self._formats = tuple(formats)
        self._log = logger or logging.getLogger(__name__)

    def _save(self, fig, filename: str) -> Path:
        path = save_figure(fig, self._dir / filename, dpi=self._dpi, formats=self._formats)
        self._log.debug(f"Heatmap tersimpan: {path.name}")
        return path

    @styled
    def heatmap_matrix(
        self,
        matrix: np.ndarray,
        row_labels: Sequence[str],
        col_labels: Sequence[str],
        filename: str,
        title: str = "Heatmap",
        cbar_label: str = "Nilai",
        cmap: str = "viridis",
        annotate: bool = True,
    ) -> Path:
        """Gambar heatmap generik dari matriks 2D.

        Args:
            matrix: matriks nilai (n_baris x n_kolom), ``np.nan`` untuk sel kosong.
            row_labels: label sumbu Y.
            col_labels: label sumbu X.
            filename: nama file PNG keluaran.
            title: judul plot.
            cbar_label: label colorbar.
            cmap: nama colormap matplotlib.
            annotate: tulis nilai numerik di tiap sel (dimatikan otomatis
                jika matriks terlalu besar untuk tetap terbaca).

        Returns:
            Path file PNG yang ditulis.
        """
        n_rows, n_cols = matrix.shape
        fig_w = max(6.0, 0.6 * n_cols + 2)
        fig_h = max(4.0, 0.5 * n_rows + 2)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))

        cmap_obj = plt.get_cmap(cmap).with_extremes(bad="#e0e0e0")
        masked = np.ma.masked_invalid(matrix)
        im = ax.imshow(masked, cmap=cmap_obj, aspect="auto")

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(col_labels, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(row_labels, fontsize=8)

        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label(cbar_label)

        if annotate and n_rows * n_cols <= 400:
            vmin, vmax = np.nanmin(matrix), np.nanmax(matrix)
            mid = (vmin + vmax) / 2 if np.isfinite(vmin) and np.isfinite(vmax) else 0
            for i in range(n_rows):
                for j in range(n_cols):
                    val = matrix[i, j]
                    if np.isnan(val):
                        continue
                    color = "white" if val > mid else "black"
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)

        ax.set_title(title)
        fig.tight_layout()

        return self._save(fig, filename)

    def heatmap_affinity(
        self,
        docking_rows: List[Dict[str, Any]],
        filename: str = "heatmap_afinitas.png",
        receptor_key: str = "receptor",
        ligand_key: str = "ligand",
        value_key: str = "affinity_best",
        title: str = "Heatmap Afinitas Docking (Reseptor x Ligan)",
    ) -> Optional[Path]:
        """Heatmap afinitas docking, baris = reseptor, kolom = ligan.

        Args:
            docking_rows: daftar dict berisi minimal ``receptor_key``,
                ``ligand_key``, ``value_key`` (mis. hasil ``compute_replicate_stats()``).
            filename: nama file PNG keluaran.
            receptor_key, ligand_key, value_key: nama field di setiap dict.
            title: judul plot.

        Returns:
            Path PNG, atau ``None`` jika tidak ada data.
        """
        if not docking_rows:
            self._log.warning("Heatmap afinitas dilewati: tidak ada data docking.")
            return None

        receptors = sorted({r[receptor_key] for r in docking_rows})
        ligands = sorted({r[ligand_key] for r in docking_rows})
        r_idx = {r: i for i, r in enumerate(receptors)}
        l_idx = {l: i for i, l in enumerate(ligands)}

        matrix = np.full((len(receptors), len(ligands)), np.nan)
        for row in docking_rows:
            matrix[r_idx[row[receptor_key]], l_idx[row[ligand_key]]] = row[value_key]

        return self.heatmap_matrix(
            matrix, receptors, ligands, filename, title=title,
            cbar_label="Afinitas (kcal/mol)", cmap="viridis_r", annotate=True,
        )

    @styled
    def heatmap_properties(
        self,
        rows: List[Dict[str, Any]],
        properties: List[str],
        filename: str = "heatmap_properti.png",
        label_key: str = "ligand",
        title: str = "Heatmap Properti (Ligan x Parameter)",
        normalize: bool = True,
    ) -> Optional[Path]:
        """Heatmap properti numerik (mis. ADMET/fisikokimia), baris = ligan,
        kolom = parameter.

        Args:
            rows: daftar dict, satu per ligan, berisi ``label_key`` + tiap
                nama field di ``properties``.
            properties: daftar nama field numerik yang jadi kolom heatmap.
            filename: nama file PNG keluaran.
            label_key: field nama ligan.
            title: judul plot.
            normalize: z-score per kolom sebelum digambar, supaya parameter
                dengan satuan/skala berbeda (mis. MW dalam Dalton vs
                probabilitas 0-1) tetap sebanding secara visual. Nilai asli
                tetap dianotasikan di tiap sel, hanya warnanya yang ternormalisasi.

        Returns:
            Path PNG, atau ``None`` jika tidak ada baris dengan data lengkap.
        """
        valid_rows = [r for r in rows if all(r.get(p) is not None for p in properties)]
        if not valid_rows:
            self._log.warning("Heatmap properti dilewati: tidak ada ligan dengan data lengkap untuk semua parameter.")
            return None

        labels = [r[label_key] for r in valid_rows]
        raw = np.array([[float(r[p]) for p in properties] for r in valid_rows])

        display = raw
        if normalize:
            mean = raw.mean(axis=0)
            std = raw.std(axis=0)
            std = np.where(std == 0, 1.0, std)
            display = (raw - mean) / std

        fig_w = max(6.0, 0.6 * len(properties) + 2)
        fig_h = max(4.0, 0.4 * len(labels) + 2)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        im = ax.imshow(display, cmap="coolwarm" if normalize else "viridis", aspect="auto")

        ax.set_xticks(range(len(properties)))
        ax.set_xticklabels(properties, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)

        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("Z-score" if normalize else "Nilai")

        if len(labels) * len(properties) <= 400:
            for i in range(len(labels)):
                for j in range(len(properties)):
                    ax.text(j, i, format_cell_value(raw[i, j]), ha="center", va="center", fontsize=7,
                            color="white" if abs(display[i, j]) > 1 else "black")

        ax.set_title(title)
        fig.tight_layout()

        return self._save(fig, filename)

    @styled
    def heatmap_clustered(
        self,
        matrix: np.ndarray,
        row_labels: Sequence[str],
        col_labels: Sequence[str],
        filename: str = "heatmap_klaster.png",
        title: str = "Heatmap Terklaster",
        cbar_label: str = "Nilai",
        cmap: "str | Colormap" = "viridis",
        cluster_rows: bool = True,
        cluster_cols: bool = True,
        method: str = "ward",
        metric: str = "euclidean",
        cbar_ticks: Optional[Sequence[float]] = None,
        cbar_ticklabels: Optional[Sequence[str]] = None,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ) -> Optional[Path]:
        """Heatmap dengan dendrogram hierarchical clustering di baris dan/atau kolom.

        Baris/kolom disusun ulang sesuai hasil clustering (bukan hanya
        diwarnai apa adanya), sehingga baris/kolom yang mirip mengelompok
        secara visual, didampingi dendrogram di tepi kiri/atas.

        Args:
            matrix: matriks nilai LENGKAP (n_baris x n_kolom), tanpa NaN
                (``linkage`` butuh data lengkap untuk menghitung jarak).
            row_labels, col_labels: label sumbu.
            filename: nama file PNG keluaran.
            title: judul plot.
            cbar_label: label colorbar.
            cmap: nama colormap matplotlib atau objek ``Colormap``.
            cluster_rows, cluster_cols: aktifkan clustering per sumbu.
            method, metric: parameter ``scipy.cluster.hierarchy.linkage``.
            cbar_ticks, cbar_ticklabels: posisi dan teks tick colorbar (mis.
                "Tidak"/"Ya" untuk matriks biner).
            vmin, vmax: rentang warna; default mengikuti data.

        Returns:
            Path PNG, atau ``None`` jika matriks kosong/mengandung NaN, atau
            sumbu yang minta di-cluster punya < 3 anggota.
        """
        from scipy.cluster.hierarchy import dendrogram, linkage

        if matrix.size == 0:
            self._log.warning("Heatmap klaster dilewati: matriks kosong.")
            return None
        if np.isnan(matrix).any():
            self._log.warning(
                "Heatmap klaster dilewati: matriks mengandung nilai kosong (NaN), "
                "hierarchical clustering butuh data lengkap tanpa NaN."
            )
            return None

        n_rows, n_cols = matrix.shape
        if cluster_rows and n_rows < 3:
            self._log.info("Clustering baris dilewati: butuh minimal 3 baris.")
            cluster_rows = False
        if cluster_cols and n_cols < 3:
            self._log.info("Clustering kolom dilewati: butuh minimal 3 kolom.")
            cluster_cols = False

        row_order = list(range(n_rows))
        col_order = list(range(n_cols))
        row_linkage = col_linkage = None

        if cluster_rows:
            row_linkage = linkage(matrix, method=method, metric=metric)
            row_order = dendrogram(row_linkage, no_plot=True)["leaves"]
        if cluster_cols:
            col_linkage = linkage(matrix.T, method=method, metric=metric)
            col_order = dendrogram(col_linkage, no_plot=True)["leaves"]

        ordered = matrix[np.ix_(row_order, col_order)]
        ordered_row_labels = [row_labels[i] for i in row_order]
        ordered_col_labels = [col_labels[j] for j in col_order]

        has_row_dendro = row_linkage is not None
        has_col_dendro = col_linkage is not None

        label_chars = max((len(str(label)) for label in row_labels), default=8)
        widths = [1.05 if has_row_dendro else 0.02, max(4.2, 0.42 * n_cols), 0.09 * label_chars + 0.35, 0.3]
        fig_w = sum(widths) + 0.6
        fig_h = max(5.0, 0.4 * n_rows + 3)
        fig = plt.figure(figsize=(fig_w, fig_h))
        # Colorbar memakai kolom gridspec sendiri (bukan ax=ax_heatmap yang menyusutkan
        # heatmap setelah dendrogram digambar), kolom 2 kosong untuk ruang label baris.
        gs = fig.add_gridspec(
            2, 4,
            width_ratios=widths,
            height_ratios=[1.0, 4.0] if has_col_dendro else [0.001, 4.0],
            wspace=0.05, hspace=0.02,
        )

        ax_heatmap = fig.add_subplot(gs[1, 1])
        im = ax_heatmap.imshow(ordered, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)
        ax_heatmap.set_xticks(range(n_cols))
        ax_heatmap.set_xticklabels(ordered_col_labels, rotation=45, ha="right", fontsize=8)
        ax_heatmap.set_yticks(range(n_rows))
        ax_heatmap.set_yticklabels(ordered_row_labels, fontsize=8)
        ax_heatmap.yaxis.tick_right()

        if has_col_dendro:
            ax_col = fig.add_subplot(gs[0, 1])
            dendrogram(col_linkage, ax=ax_col, no_labels=True, color_threshold=0,
                       above_threshold_color="#444444")
            ax_col.axis("off")
        if has_row_dendro:
            ax_row = fig.add_subplot(gs[1, 0])
            dendrogram(row_linkage, ax=ax_row, orientation="left", no_labels=True,
                       color_threshold=0, above_threshold_color="#444444")
            ax_row.invert_yaxis()  # scipy menaruh leaf 0 di bawah, imshow di atas
            ax_row.axis("off")

        ax_cbar = fig.add_subplot(gs[1, 3])
        colorbar = fig.colorbar(im, cax=ax_cbar, label=cbar_label)
        if cbar_ticks is not None:
            colorbar.set_ticks(list(cbar_ticks))
            if cbar_ticklabels is not None:
                colorbar.set_ticklabels(list(cbar_ticklabels))
        fig.suptitle(title)

        return self._save(fig, filename)

    def heatmap_properties_clustered(
        self,
        rows: List[Dict[str, Any]],
        properties: List[str],
        filename: str = "heatmap_properti_klaster.png",
        label_key: str = "ligand",
        title: str = "Heatmap Properti Terklaster (Ligan x Parameter)",
        normalize: bool = True,
        method: str = "ward",
        metric: str = "euclidean",
    ) -> Optional[Path]:
        """Heatmap terklaster untuk properti numerik (ADMET/fisikokimia).

        Sama seperti ``heatmap_properties`` tapi baris (ligan) dan kolom
        (parameter, jika >= 3) disusun ulang sesuai hierarchical clustering,
        lengkap dengan dendrogram.

        Args:
            rows: daftar dict, satu per ligan.
            properties: daftar nama field numerik yang jadi kolom.
            filename: nama file PNG keluaran.
            label_key: field nama ligan.
            title: judul plot.
            normalize: z-score per kolom sebelum clustering & digambar,
                supaya parameter beda skala tetap sebanding.
            method, metric: parameter ``scipy.cluster.hierarchy.linkage``.

        Returns:
            Path PNG, atau ``None`` jika tidak ada ligan dengan data lengkap.
        """
        valid_rows = [r for r in rows if all(r.get(p) is not None for p in properties)]
        if not valid_rows:
            self._log.warning("Heatmap properti terklaster dilewati: tidak ada ligan dengan data lengkap.")
            return None

        labels = [r[label_key] for r in valid_rows]
        raw = np.array([[float(r[p]) for p in properties] for r in valid_rows])

        matrix = raw
        if normalize:
            mean = raw.mean(axis=0)
            std = raw.std(axis=0)
            std = np.where(std == 0, 1.0, std)
            matrix = (raw - mean) / std

        return self.heatmap_clustered(
            matrix, labels, properties, filename=filename, title=title,
            cbar_label="Z-score" if normalize else "Nilai",
            cmap="coolwarm" if normalize else "viridis",
            cluster_cols=len(properties) >= 3, method=method, metric=metric,
        )
