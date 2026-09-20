"""
Heatmap matriks nilai untuk visualisasi hasil chemflow: afinitas docking
(reseptor x ligan) dan properti ADMET (ligan x parameter).

Matriks yang lebih besar dari ``max_rows`` x ``max_cols`` dipotong otomatis
menjadi ubin (``_part01of06``) supaya sel dan label tetap terbaca. Skala warna
dihitung dari seluruh matriks (dan klaster dari seluruh data) sebelum dipotong,
jadi antar-ubin sebanding. Semua metode mengembalikan ``List[Path]``, kosong
bila heatmap dilewati.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap, Normalize
from matplotlib.patches import Patch

from chemflow.analytics.paging import paged_name, paginate_grid
from chemflow.analytics.style import (
    DEFAULT_MAX_COLS, DEFAULT_MAX_ROWS, FIG_DPI, color_tick_labels, group_colors, save_figure, styled,
    text_color_for,
)

_ANNOTATE_MAX_CELLS = 600


def format_cell_value(value: float) -> str:
    """Angka sel ringkas tanpa notasi ilmiah: 0 desimal untuk >= 100, 1 untuk >= 10, 2 untuk sisanya."""
    magnitude = abs(value)
    digits = 0 if magnitude >= 100 else 1 if magnitude >= 10 else 2
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _color_range(matrix: np.ndarray, vmin: Optional[float], vmax: Optional[float]):
    """Rentang warna global; ``None`` bila matriks tak punya nilai terbatas."""
    finite = matrix[np.isfinite(matrix)]
    if finite.size == 0:
        return None
    lo = float(finite.min()) if vmin is None else vmin
    hi = float(finite.max()) if vmax is None else vmax
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


class HeatmapBuilder:
    """Pembuat heatmap untuk matriks reseptor x ligan atau ligan x properti."""

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

    def _save(self, fig, filename: str) -> Path:
        path = save_figure(fig, self._dir / filename, dpi=self._dpi, formats=self._formats)
        self._log.debug(f"Heatmap tersimpan: {path.name}")
        return path

    @staticmethod
    def _color_groups(fig, texts, labels: Sequence[str], groups: Optional[Mapping[str, str]]) -> None:
        """Warnai teks label sumbu menurut grup dan tambahkan legenda grup di bawah gambar."""
        if not groups:
            return
        present = [groups.get(str(label)) for label in labels]
        distinct = list(dict.fromkeys(g for g in present if g))
        if len(distinct) < 2:
            return
        colors = group_colors(distinct)
        color_tick_labels(texts, present, colors)
        handles = [Patch(color=colors[g], label=g) for g in distinct]
        fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 4), title="Grup",
                   frameon=False, fontsize=8)

    @styled
    def heatmap_matrix(
        self,
        matrix: np.ndarray,
        row_labels: Sequence[str],
        col_labels: Sequence[str],
        filename: str,
        title: str = "Heatmap",
        cbar_label: str = "Nilai",
        cmap: "str | Colormap" = "viridis",
        annotate: bool = True,
        *,
        annotation_values: Optional[np.ndarray] = None,
        annotation_fmt: Optional[Callable[[float], str]] = None,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        row_groups: Optional[Mapping[str, str]] = None,
        col_groups: Optional[Mapping[str, str]] = None,
        pinned_cols: Sequence[int] = (),
        cbar_ticks: Optional[Sequence[float]] = None,
        cbar_ticklabels: Optional[Sequence[str]] = None,
    ) -> List[Path]:
        """Gambar heatmap generik dari matriks 2D, dipotong otomatis bila terlalu besar.

        Args:
            matrix: matriks nilai (n_baris x n_kolom), ``np.nan`` untuk sel kosong.
            row_labels: label sumbu Y.
            col_labels: label sumbu X.
            filename: nama file PNG keluaran (ubin ke-n diberi akhiran ``_partNNofMM``).
            title: judul plot.
            cbar_label: label colorbar.
            cmap: nama colormap matplotlib atau objek ``Colormap``.
            annotate: tulis nilai numerik di tiap sel (dimatikan otomatis jika satu ubin
                terlalu besar untuk tetap terbaca).
            annotation_values: matriks nilai yang ditulis di sel bila berbeda dari ``matrix``
                (mis. nilai asli, sementara warna memakai z-score).
            annotation_fmt: pemformat angka sel; default dua desimal.
            vmin, vmax: rentang warna; default mengikuti seluruh matriks.
            row_groups, col_groups: peta label -> grup; teks label diwarnai per grup.
            pinned_cols: indeks kolom yang selalu ikut di setiap ubin (mis. kolom Native).
            cbar_ticks, cbar_ticklabels: posisi dan teks tick colorbar (mis. Buruk/Sedang/Baik).

        Returns:
            Daftar path PNG, kosong bila matriks kosong atau tanpa nilai.
        """
        matrix = np.asarray(matrix, dtype=float)
        if matrix.ndim != 2 or matrix.size == 0:
            self._log.warning(f"Heatmap '{filename}' dilewati: matriks kosong.")
            return []
        scale = _color_range(matrix, vmin, vmax)
        if scale is None:
            self._log.warning(f"Heatmap '{filename}' dilewati: tidak ada nilai yang bisa digambar.")
            return []
        lo, hi = scale
        n_rows, n_cols = matrix.shape

        pinned = [c for c in dict.fromkeys(pinned_cols) if 0 <= c < n_cols]
        free = [j for j in range(n_cols) if j not in pinned]
        if not free:
            pinned, free = [], list(range(n_cols))

        cmap_obj = plt.get_cmap(cmap).with_extremes(bad="#e0e0e0")
        norm = Normalize(vmin=lo, vmax=hi)
        fmt = annotation_fmt or (lambda v: f"{v:.2f}")
        shown = annotation_values if annotation_values is not None else matrix

        paths: List[Path] = []
        for tile in paginate_grid(n_rows, len(free), self._max_rows, self._max_cols):
            rows = list(range(tile.rows.start, tile.rows.stop))
            cols = pinned + [free[k] for k in range(tile.cols.start, tile.cols.stop)]
            sub = matrix[np.ix_(rows, cols)]
            sub_labels_r = [str(row_labels[i]) for i in rows]
            sub_labels_c = [str(col_labels[j]) for j in cols]

            fig_w = max(6.0, 0.6 * len(cols) + 2)
            fig_h = max(4.0, 0.45 * len(rows) + 2)
            fig, ax = plt.subplots(figsize=(fig_w, fig_h))
            im = ax.imshow(np.ma.masked_invalid(sub), cmap=cmap_obj, norm=norm, aspect="auto")

            ax.set_xticks(range(len(cols)))
            xt = ax.set_xticklabels(sub_labels_c, rotation=45, ha="right", fontsize=8)
            ax.set_yticks(range(len(rows)))
            yt = ax.set_yticklabels(sub_labels_r, fontsize=8)
            if pinned:
                ax.axvline(len(pinned) - 0.5, color="#222222", linewidth=1.6)

            cbar = fig.colorbar(im, ax=ax)
            cbar.set_label(cbar_label)
            if cbar_ticks is not None:
                cbar.set_ticks(list(cbar_ticks))
                if cbar_ticklabels is not None:
                    cbar.set_ticklabels(list(cbar_ticklabels))

            if annotate and len(rows) * len(cols) <= _ANNOTATE_MAX_CELLS:
                for i, r in enumerate(rows):
                    for j, c in enumerate(cols):
                        value = sub[i, j]
                        if not np.isfinite(value):
                            continue
                        ax.text(j, i, fmt(float(shown[r, c])), ha="center", va="center", fontsize=7,
                                color=text_color_for(cmap_obj(norm(value))))

            ax.set_title(title + tile.title_suffix)
            self._color_groups(fig, yt, sub_labels_r, row_groups)
            self._color_groups(fig, xt, sub_labels_c, col_groups)
            fig.tight_layout(rect=(0, 0.07, 1, 1) if (row_groups or col_groups) else None)
            paths.append(self._save(fig, paged_name(filename, tile)))
        return paths

    def heatmap_affinity(
        self,
        docking_rows: List[Dict[str, Any]],
        filename: str = "heatmap_afinitas.png",
        receptor_key: str = "receptor",
        ligand_key: str = "ligand",
        value_key: str = "affinity_best",
        title: str = "Heatmap Afinitas Docking (Reseptor x Ligan)",
        *,
        native_rows: Optional[List[Dict[str, Any]]] = None,
        col_groups: Optional[Mapping[str, str]] = None,
    ) -> List[Path]:
        """Heatmap afinitas docking, baris = reseptor, kolom = ligan.

        Args:
            docking_rows: daftar dict berisi minimal ``receptor_key``,
                ``ligand_key``, ``value_key`` (mis. hasil ``compute_replicate_stats()``).
            filename: nama file PNG keluaran.
            receptor_key, ligand_key, value_key: nama field di setiap dict.
            title: judul plot.
            native_rows: baris ΔG ligan native. Ditampilkan sebagai kolom "Native (ref)" yang
                selalu ikut di setiap ubin: tiap reseptor dibandingkan dengan native-nya sendiri.
            col_groups: peta ligan -> grup untuk mewarnai label kolom.

        Returns:
            Daftar path PNG, kosong jika tidak ada data.
        """
        from chemflow.analytics.group_stats import NATIVE_GROUP, NATIVE_LABEL

        if not docking_rows:
            self._log.warning("Heatmap afinitas dilewati: tidak ada data docking.")
            return []

        receptors = sorted({r[receptor_key] for r in docking_rows} | {r[receptor_key] for r in (native_rows or [])})
        ligands = sorted({r[ligand_key] for r in docking_rows})
        r_idx = {r: i for i, r in enumerate(receptors)}
        offset = 1 if native_rows else 0
        l_idx = {l: i + offset for i, l in enumerate(ligands)}

        matrix = np.full((len(receptors), len(ligands) + offset), np.nan)
        for row in docking_rows:
            matrix[r_idx[row[receptor_key]], l_idx[row[ligand_key]]] = row[value_key]

        columns = list(ligands)
        groups = dict(col_groups or {})
        if native_rows:
            for row in native_rows:
                i = r_idx[row[receptor_key]]
                value = row[value_key]
                if value is not None and (np.isnan(matrix[i, 0]) or value < matrix[i, 0]):
                    matrix[i, 0] = value
            columns = [NATIVE_LABEL] + columns
            groups[NATIVE_LABEL] = NATIVE_GROUP

        return self.heatmap_matrix(
            matrix, receptors, columns, filename, title=title,
            cbar_label="Afinitas (kcal/mol)", cmap="viridis_r", annotate=True,
            col_groups=groups or None, pinned_cols=[0] if native_rows else (),
        )

    def heatmap_properties(
        self,
        rows: List[Dict[str, Any]],
        properties: List[str],
        filename: str = "heatmap_properti.png",
        label_key: str = "ligand",
        title: str = "Heatmap Properti (Ligan x Parameter)",
        normalize: bool = True,
        *,
        row_groups: Optional[Mapping[str, str]] = None,
    ) -> List[Path]:
        """Heatmap properti numerik (mis. ADMET/fisikokimia), baris = ligan,
        kolom = parameter.

        Args:
            rows: daftar dict, satu per ligan, berisi ``label_key`` + tiap
                nama field di ``properties``.
            properties: daftar nama field numerik yang jadi kolom heatmap.
            filename: nama file PNG keluaran.
            label_key: field nama ligan.
            title: judul plot.
            normalize: z-score per kolom (dihitung pada semua ligan, sebelum dipotong) supaya
                parameter dengan satuan/skala berbeda (mis. MW dalam Dalton vs
                probabilitas 0-1) tetap sebanding secara visual. Nilai asli
                tetap dianotasikan di tiap sel, hanya warnanya yang ternormalisasi.
            row_groups: peta ligan -> grup untuk mewarnai label baris.

        Returns:
            Daftar path PNG, kosong jika tidak ada baris dengan data lengkap.
        """
        valid_rows = [r for r in rows if all(r.get(p) is not None for p in properties)]
        if not valid_rows:
            self._log.warning("Heatmap properti dilewati: tidak ada ligan dengan data lengkap untuk semua parameter.")
            return []

        labels = [r[label_key] for r in valid_rows]
        raw = np.array([[float(r[p]) for p in properties] for r in valid_rows])

        display = raw
        if normalize:
            mean = raw.mean(axis=0)
            std = raw.std(axis=0)
            std = np.where(std == 0, 1.0, std)
            display = (raw - mean) / std

        return self.heatmap_matrix(
            display, labels, properties, filename, title=title,
            cbar_label="Z-score" if normalize else "Nilai", cmap="coolwarm" if normalize else "viridis",
            annotation_values=raw, annotation_fmt=format_cell_value, row_groups=row_groups,
        )

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
        row_groups: Optional[Mapping[str, str]] = None,
        col_groups: Optional[Mapping[str, str]] = None,
    ) -> List[Path]:
        """Heatmap dengan dendrogram hierarchical clustering di baris dan/atau kolom.

        Baris/kolom disusun ulang sesuai hasil clustering (bukan hanya
        diwarnai apa adanya), sehingga baris/kolom yang mirip mengelompok
        secara visual, didampingi dendrogram di tepi kiri/atas. Klaster dihitung
        sekali pada matriks penuh; bila matriks terlalu besar, hasil yang sudah
        terurut dipotong menjadi ubin dan tiap ubin memperlihatkan potongan
        dendrogram penuh yang sama pada jendela barisnya.

        Args:
            matrix: matriks nilai lengkap (n_baris x n_kolom), tanpa NaN
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
            row_groups, col_groups: peta label -> grup untuk mewarnai label.

        Returns:
            Daftar path PNG, kosong jika matriks kosong/mengandung NaN, atau
            sumbu yang minta di-cluster punya < 3 anggota.
        """
        from scipy.cluster.hierarchy import dendrogram, linkage

        matrix = np.asarray(matrix, dtype=float)
        if matrix.size == 0:
            self._log.warning("Heatmap klaster dilewati: matriks kosong.")
            return []
        if np.isnan(matrix).any():
            self._log.warning(
                "Heatmap klaster dilewati: matriks mengandung nilai kosong (NaN), "
                "hierarchical clustering butuh data lengkap tanpa NaN."
            )
            return []

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
        ordered_row_labels = [str(row_labels[i]) for i in row_order]
        ordered_col_labels = [str(col_labels[j]) for j in col_order]
        scale = _color_range(ordered, vmin, vmax)
        if scale is None:
            self._log.warning(f"Heatmap klaster '{filename}' dilewati: tidak ada nilai yang bisa digambar.")
            return []
        lo, hi = scale

        has_row_dendro = row_linkage is not None
        has_col_dendro = col_linkage is not None

        paths: List[Path] = []
        for tile in paginate_grid(n_rows, n_cols, self._max_rows, self._max_cols):
            r0, r1, c0, c1 = tile.rows.start, tile.rows.stop, tile.cols.start, tile.cols.stop
            sub = ordered[r0:r1, c0:c1]
            sub_rows, sub_cols = ordered_row_labels[r0:r1], ordered_col_labels[c0:c1]

            label_chars = max((len(label) for label in sub_rows), default=8)
            widths = [1.05 if has_row_dendro else 0.02, max(4.2, 0.42 * (c1 - c0)), 0.09 * label_chars + 0.35, 0.3]
            fig_w = sum(widths) + 0.6
            fig_h = max(5.0, 0.4 * (r1 - r0) + 3)
            fig = plt.figure(figsize=(fig_w, fig_h))
            # Colorbar memakai kolom gridspec sendiri (bukan ax=ax_heatmap yang menyusutkan
            # heatmap setelah dendrogram digambar), kolom 2 kosong untuk ruang label baris.
            grid_extra = {"bottom": 0.22} if (row_groups or col_groups) else {}   # ruang legenda grup
            gs = fig.add_gridspec(
                2, 4,
                width_ratios=widths,
                height_ratios=[1.0, 4.0] if has_col_dendro else [0.001, 4.0],
                wspace=0.05, hspace=0.02, **grid_extra,
            )

            ax_heatmap = fig.add_subplot(gs[1, 1])
            im = ax_heatmap.imshow(sub, cmap=cmap, aspect="auto", vmin=lo, vmax=hi)
            ax_heatmap.set_xticks(range(c1 - c0))
            xt = ax_heatmap.set_xticklabels(sub_cols, rotation=45, ha="right", fontsize=8)
            ax_heatmap.yaxis.tick_right()   # sebelum set_yticklabels, supaya teks yang diwarnai adalah yang tampil
            ax_heatmap.set_yticks(range(r1 - r0))
            ax_heatmap.set_yticklabels(sub_rows, fontsize=8)
            yt = ax_heatmap.get_yticklabels()

            # Daun ke-k dendrogram berada di posisi 10k+5, jadi jendela [a, b) = [10a, 10b].
            if has_col_dendro:
                ax_col = fig.add_subplot(gs[0, 1])
                dendrogram(col_linkage, ax=ax_col, no_labels=True, color_threshold=0,
                           above_threshold_color="#444444")
                ax_col.set_xlim(10 * c0, 10 * c1)
                ax_col.axis("off")
            if has_row_dendro:
                ax_row = fig.add_subplot(gs[1, 0])
                dendrogram(row_linkage, ax=ax_row, orientation="left", no_labels=True,
                           color_threshold=0, above_threshold_color="#444444")
                ax_row.set_ylim(10 * r1, 10 * r0)  # terbalik: scipy menaruh daun 0 di bawah, imshow di atas
                ax_row.axis("off")

            ax_cbar = fig.add_subplot(gs[1, 3])
            colorbar = fig.colorbar(im, cax=ax_cbar, label=cbar_label)
            if cbar_ticks is not None:
                colorbar.set_ticks(list(cbar_ticks))
                if cbar_ticklabels is not None:
                    colorbar.set_ticklabels(list(cbar_ticklabels))
            fig.suptitle(title + tile.title_suffix)
            self._color_groups(fig, yt, sub_rows, row_groups)
            self._color_groups(fig, xt, sub_cols, col_groups)
            paths.append(self._save(fig, paged_name(filename, tile)))
        return paths

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
        *,
        row_groups: Optional[Mapping[str, str]] = None,
    ) -> List[Path]:
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
            row_groups: peta ligan -> grup untuk mewarnai label baris.

        Returns:
            Daftar path PNG, kosong jika tidak ada ligan dengan data lengkap.
        """
        valid_rows = [r for r in rows if all(r.get(p) is not None for p in properties)]
        if not valid_rows:
            self._log.warning("Heatmap properti terklaster dilewati: tidak ada ligan dengan data lengkap.")
            return []

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
            cluster_cols=len(properties) >= 3, method=method, metric=metric, row_groups=row_groups,
        )
