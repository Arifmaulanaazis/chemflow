"""
Grafik utama hasil chemflow: bar afinitas, radar gabungan, radar per kategori
ADMET, dan bar klasifikasi ADMET.

Semua grafik memakai gaya bersama ``analytics.style`` (palet aman buta warna,
300 dpi) dan ditulis sebagai PNG, dengan format vektor tambahan opsional.
Radar gabungan menormalisasi tiap kriteria min-max lintas ligan yang
dibandingkan; radar ADMET memakai skor klasifikasi (baik 1, sedang 0,5,
buruk 0) sehingga parameter berbeda satuan tetap sebanding.

Grafik yang memuat banyak ligan dipotong otomatis menjadi beberapa bagian
(``_part01of03``) supaya tetap terbaca; normalisasi dan batas sumbu dihitung
dari seluruh data sebelum dipotong sehingga antar-bagian sebanding. Semua
metode grafik mengembalikan ``List[Path]`` (kosong bila grafik dilewati).
Ligan native (``highlight_keys`` / ``pinned``) diberi warna berbeda dan
disematkan di setiap bagian radar sebagai pembanding.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from chemflow.admet.admet_rules import (
    CAT_PHYSICOCHEMICAL, CATEGORIES, FLAG_SCORE, Flag, classify_admet_value, rules_by_category,
)
from chemflow.analytics.paging import Page, paged_name, paginate
from chemflow.analytics.style import (
    COLOR_GOOD, COLOR_MEDIUM, COLOR_NATIVE, COLOR_POOR, DEFAULT_MAX_ROWS, FIG_DPI, MAX_RADAR_PAGES,
    MAX_RADAR_SERIES, PALETTE, chart_style, clean_axes, save_figure,
)

_MAX_PINNED = 3


def _wrap(text: str, width: int = 18) -> str:
    return textwrap.fill(str(text), width=width, break_long_words=False)


class ChartBuilder:
    """Pembuat grafik bar dan radar untuk hasil pipeline chemflow."""

    def __init__(self, output_dir: "str | Path", dpi: int = FIG_DPI, formats: Sequence[str] = ("png",),
                 logger: Optional[logging.Logger] = None, max_rows: Optional[int] = DEFAULT_MAX_ROWS) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dpi = dpi
        self._formats = tuple(formats)
        self._log = logger or logging.getLogger(__name__)
        self._max_rows = max_rows

    def _save(self, fig, filename: str) -> Path:
        path = save_figure(fig, self._dir / filename, dpi=self._dpi, formats=self._formats)
        self._log.debug(f"Grafik tersimpan: {path.name}")
        return path

    def bar_affinity(self, rows: List[Dict[str, Any]], *, ligand_key: str = "ligand",
                     value_key: str = "affinity_best", title: str = "Afinitas Docking Terbaik",
                     top_n: Optional[int] = None, filename: str = "bar_affinity.png",
                     highlight_keys: Optional[Set[str]] = None) -> List[Path]:
        """Bar horizontal afinitas per ligan (lebih negatif berarti ikatan lebih kuat).

        Bila ligan lebih banyak dari ``max_rows``, grafik dipotong menjadi beberapa bagian
        berurutan (bagian 1 = afinitas terbaik) dengan sumbu x yang sama.

        Args:
            rows: daftar dict berisi ``ligand_key`` dan ``value_key``.
            ligand_key, value_key: nama field di setiap dict.
            title: judul grafik.
            top_n: batasi ke N afinitas terbaik; None berarti semua.
            filename: nama file PNG keluaran (bagian ke-n diberi akhiran ``_partNNofMM``).
            highlight_keys: label yang diwarnai sebagai ligan native; bila hanya satu nilai native,
                digambar juga garis referensinya.

        Returns:
            Daftar path PNG yang ditulis (kosong bila tak ada data).
        """
        data = sorted(rows, key=lambda r: r[value_key])
        if top_n:
            data = data[:top_n]
        if not data:
            return []
        highlight = set(highlight_keys or ())
        labels = [str(r[ligand_key]) for r in data]
        values = np.array([float(r[value_key]) for r in data])

        span = max(1.0, float(np.abs(values).max()))
        xlim = (min(0.0, values.min()) - 0.14 * span, max(0.0, values.max()) + 0.06 * span)
        native_values = [v for lab, v in zip(labels, values) if lab in highlight]

        paths: List[Path] = []
        for page in paginate(len(labels), self._max_rows):
            page_labels, page_values = page.slice(labels), page.slice(values)
            with chart_style():
                fig, ax = plt.subplots(figsize=(8.0, max(3.2, 0.32 * len(page_labels) + 1.4)))
                colors = [COLOR_NATIVE if lab in highlight else (PALETTE[0] if v < 0 else PALETTE[1])
                          for lab, v in zip(page_labels, page_values)]
                ypos = np.arange(len(page_labels))
                ax.barh(ypos, page_values, color=colors, height=0.72, edgecolor="none")
                ax.set_yticks(ypos)
                ax.set_yticklabels(page_labels)
                ax.invert_yaxis()
                ax.axvline(0, color="#444444", linewidth=0.8)
                ax.set_xlabel("Afinitas docking (kcal/mol)")
                ax.set_title(title + page.title_suffix)
                clean_axes(ax, grid_axis="x")

                ax.set_xlim(*xlim)
                for y, v in zip(ypos, page_values):
                    ax.annotate(f"{v:.2f}", (v, y), xytext=(-4 if v < 0 else 4, 0), textcoords="offset points",
                                ha="right" if v < 0 else "left", va="center", fontsize=8, color="#222222")

                if native_values:
                    handles = [Patch(color=COLOR_NATIVE, label="Ligan native")]
                    if len(native_values) == 1:
                        ax.axvline(native_values[0], color=COLOR_NATIVE, linestyle="--", linewidth=1.2, zorder=1)
                    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.2), frameon=False)
                paths.append(self._save(fig, paged_name(filename, page)))
        return paths

    def radar_combined(
        self,
        ligand_rows: List[Dict[str, Any]],
        criteria: List[str],
        *,
        label_key: str = "ligand",
        title: str = "Profil Gabungan",
        lower_is_better: Optional[List[str]] = None,
        absolute: Optional[List[str]] = None,
        criteria_labels: Optional[Dict[str, str]] = None,
        top_n: int = MAX_RADAR_SERIES,
        rank_by: Optional[str] = None,
        filename: str = "radar_combined.png",
        pinned: Optional[Set[str]] = None,
        max_pages: int = MAX_RADAR_PAGES,
    ) -> List[Path]:
        """Radar multi-kriteria (afinitas, fisikokimia, skor kategori ADMET).

        Kriteria dinormalisasi 0-1 (min-max lintas semua ligan) supaya satuan yang
        berbeda tetap sebanding pada satu radar, kecuali kriteria pada
        ``absolute`` yang sudah berskala 0-1 dan dipakai apa adanya. Ligan diurutkan
        menurut peringkat lalu dibagi ke beberapa radar berisi ``top_n`` garis.

        Args:
            ligand_rows: daftar dict, satu per ligan, berisi ``criteria`` dan ``label_key``.
            criteria: nama field yang menjadi sumbu radar.
            label_key: field nama pada legenda.
            title: judul grafik.
            lower_is_better: subset ``criteria`` yang nilai kecilnya lebih baik
                (dibalik supaya arah baik selalu ke luar).
            absolute: subset ``criteria`` yang sudah berskala 0-1 (tanpa min-max).
            criteria_labels: nama tampilan tiap kriteria pada sumbu.
            top_n: jumlah garis per radar (per bagian).
            rank_by: kriteria penentu peringkat; ``None`` memakai skor komposit
                (rata-rata seluruh kriteria ternormalisasi).
            filename: nama file PNG keluaran (bagian ke-n diberi akhiran ``_partNNofMM``).
            pinned: label (nilai ``label_key``) yang selalu digambar di setiap bagian
                sebagai pembanding, bergaris putus-putus (mis. ligan native).
            max_pages: batas jumlah bagian; ligan berperingkat lebih rendah tidak digambar.

        Returns:
            Daftar path PNG, kosong jika tak ada ligan dengan data lengkap.
        """
        lower_is_better = set(lower_is_better or [])
        absolute = set(absolute or [])
        labels_map = criteria_labels or {}

        valid_rows = [r for r in ligand_rows if all(r.get(c) is not None for c in criteria)]
        if not valid_rows or len(criteria) < 3:
            self._log.warning("Radar gabungan dilewati: data lengkap atau jumlah kriteria (minimal 3) tidak cukup.")
            return []

        matrix = np.array([[float(r[c]) for c in criteria] for r in valid_rows])
        normalized = np.zeros_like(matrix)
        for j, crit in enumerate(criteria):
            column = matrix[:, j]
            if crit in absolute:
                normalized[:, j] = np.clip(1 - column if crit in lower_is_better else column, 0, 1)
                continue
            if crit in lower_is_better:
                column = -column
            span = column.max() - column.min()
            normalized[:, j] = (column - column.min()) / span if span > 0 else 0.5

        ranked_by_criterion = rank_by in criteria
        ranking = normalized[:, criteria.index(rank_by)] if ranked_by_criterion else normalized.mean(axis=1)
        order = [int(i) for i in np.argsort(-ranking, kind="stable")]
        basis = labels_map.get(rank_by, rank_by) if ranked_by_criterion else "skor komposit"
        axis_labels = [_wrap(labels_map.get(c, c), 14) for c in criteria]

        return self.radar_pages(
            normalized, [str(r[label_key]) for r in valid_rows], order, axis_labels, title, basis,
            ticks=[0.25, 0.5, 0.75, 1.0], tick_labels=["0,25", "0,5", "0,75", "1,0"],
            filename=filename, per_page=top_n, pinned=pinned, max_pages=max_pages, noun="ligan",
        )

    def radar_by_category(self, admet_rows: List[Dict[str, Any]], category: str, *,
                          label_key: str = "ligand", top_n: int = MAX_RADAR_SERIES, max_axes: int = 12,
                          filename: Optional[str] = None, pinned: Optional[Set[str]] = None,
                          max_pages: int = MAX_RADAR_PAGES) -> List[Path]:
        """Radar profil ADMET satu kategori: sumbu = parameter, garis = ligan.

        Tiap nilai diubah ke skor klasifikasi (baik 1, sedang 0,5, buruk 0);
        nilai tanpa data memakai 0,5 agar poligon tetap tertutup. Ligan
        diurutkan menurut rata-rata skor seluruh parameter kategori lalu dibagi
        ke beberapa radar berisi ``top_n`` garis. Jika parameter melebihi
        ``max_axes``, sumbu dibatasi ke parameter dengan variasi skor terbesar
        antar ligan supaya radar tetap terbaca (rincian lengkap ada di bar
        klasifikasi).

        Returns:
            Daftar path PNG, kosong jika kurang dari 3 parameter terskor
            tersedia pada data (radar butuh minimal 3 sumbu).
        """
        if not admet_rows:
            return []
        available = set().union(*(r.keys() for r in admet_rows))
        rules = [r for r in rules_by_category(category) if r.scored and r.column in available]
        if len(rules) < 3:
            self._log.info(f"Radar ADMET '{category}' dilewati: kurang dari 3 parameter terskor tersedia.")
            return []

        scores = []
        for row in admet_rows:
            scores.append([
                FLAG_SCORE.get(classify_admet_value(rule.column, row.get(rule.column)).flag, 0.5)
                for rule in rules
            ])
        scores = np.array(scores)
        order = [int(i) for i in np.argsort(-scores.mean(axis=1), kind="stable")]

        notes = []
        if len(rules) > max_axes:
            keep = sorted(np.argsort(-scores.var(axis=0), kind="stable")[:max_axes])
            notes.append(f"{max_axes} dari {len(rules)} parameter dengan variasi terbesar")
            rules = [rules[i] for i in keep]
            scores = scores[:, keep]
        title = f"Profil ADMET: {category}" + ("\n" + ", ".join(notes) if notes else "")

        return self.radar_pages(
            scores, [str(r[label_key]) for r in admet_rows], order, [_wrap(r.label, 14) for r in rules], title,
            "skor tertinggi", ticks=[0.0, 0.5, 1.0], tick_labels=["Buruk", "Sedang", "Baik"],
            filename=filename or f"radar_admet_{category.lower()}.png", per_page=top_n, pinned=pinned,
            max_pages=max_pages, noun="ligan",
        )

    def radar_all_admet_categories(self, admet_rows: List[Dict[str, Any]], *,
                                   label_key: str = "ligand", top_n: int = MAX_RADAR_SERIES,
                                   pinned: Optional[Set[str]] = None) -> List[Path]:
        """Satu radar (dipotong per ``top_n`` ligan) per kategori ADMET (kecuali Fisikokimia) yang punya cukup parameter."""
        paths: List[Path] = []
        for category in CATEGORIES:
            if category == CAT_PHYSICOCHEMICAL:
                continue
            paths.extend(self.radar_by_category(admet_rows, category, label_key=label_key, top_n=top_n,
                                                pinned=pinned))
        return paths

    def admet_stacked_bar(self, admet_rows: List[Dict[str, Any]], category: str,
                          filename: Optional[str] = None) -> List[Path]:
        """Bar bertumpuk 100%: persentase ligan baik/sedang/buruk untuk tiap parameter kategori.

        Returns:
            Daftar path PNG, kosong jika tak ada parameter terskor pada data.
        """
        if not admet_rows:
            return []
        available = set().union(*(r.keys() for r in admet_rows))
        labels, shares = [], []
        for rule in rules_by_category(category):
            if not rule.scored or rule.column not in available:
                continue
            flags = [classify_admet_value(rule.column, r.get(rule.column)).flag for r in admet_rows]
            counted = [f for f in flags if f in (Flag.GREEN, Flag.YELLOW, Flag.RED)]
            if not counted:
                continue
            labels.append(rule.label)
            shares.append([100.0 * counted.count(f) / len(counted) for f in (Flag.GREEN, Flag.YELLOW, Flag.RED)])
        if not labels:
            return []

        data = np.array(shares)
        base_name = filename or f"admet_klasifikasi_{category.lower()}.png"
        paths: List[Path] = []
        for page in paginate(len(labels), self._max_rows):
            page_labels, page_data = page.slice(labels), data[page.start:page.stop]
            with chart_style():
                fig, ax = plt.subplots(figsize=(8.0, max(3.0, 0.3 * len(page_labels) + 1.8)))
                ypos = np.arange(len(page_labels))
                left = np.zeros(len(page_labels))
                for column, color, name in zip(page_data.T, (COLOR_GOOD, COLOR_MEDIUM, COLOR_POOR),
                                                ("Baik", "Sedang", "Buruk")):
                    ax.barh(ypos, column, left=left, color=color, label=name, height=0.72,
                            edgecolor="white", linewidth=0.5)
                    left += column
                ax.set_yticks(ypos)
                ax.set_yticklabels(page_labels)
                ax.invert_yaxis()
                ax.set_xlim(0, 100)
                ax.set_xlabel("Persentase ligan (%)")
                ax.set_title(f"Klasifikasi ADMET: {category}{page.title_suffix}")
                clean_axes(ax)
                ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
                paths.append(self._save(fig, paged_name(base_name, page)))
        return paths

    def admet_all_stacked_bars(self, admet_rows: List[Dict[str, Any]]) -> List[Path]:
        paths: List[Path] = []
        for category in CATEGORIES:
            paths.extend(self.admet_stacked_bar(admet_rows, category))
        return paths

    def radar_pages(self, values: np.ndarray, series_labels: List[str], order: List[int],
                     axis_labels: List[str], title: str, basis: str, *, ticks: List[float],
                     tick_labels: List[str], filename: str, per_page: int, pinned: Optional[Set[str]],
                     max_pages: int, noun: str) -> List[Path]:
        """Bagi ligan berperingkat ``order`` ke radar berisi ``per_page`` garis; ligan ``pinned`` ikut di tiap bagian."""
        pinned = set(pinned or ())
        pinned_idx = [i for i in order if series_labels[i] in pinned][:_MAX_PINNED]
        ranked = [i for i in order if i not in pinned_idx]
        page_size = max(1, per_page - len(pinned_idx))

        pages = paginate(len(ranked), page_size)
        if not pages and pinned_idx:
            pages = [Page(1, 1, 0, 0)]
        if len(pages) > max_pages:
            shown = sum(p.count for p in pages[:max_pages])
            self._log.info(
                f"Radar '{filename}': {len(ranked)} {noun}, hanya {shown} berperingkat teratas yang digambar "
                f"({max_pages} bagian); sisanya dapat dilihat di heatmap dan tabel Excel."
            )
            total = max_pages
            pages = [Page(p.index, total, p.start, p.stop) for p in pages[:max_pages]]

        n_all = len(ranked) + len(pinned_idx)
        paths: List[Path] = []
        for page in pages:
            chosen = pinned_idx + ranked[page.start:page.stop]
            page_title = title
            if page.total > 1 or len(ranked) > page.stop:
                page_title += (f"\n{noun} peringkat {page.start + 1}-{page.stop} dari {n_all - len(pinned_idx)} "
                               f"menurut {basis}")
            paths.append(self._draw_radar(
                values[chosen], [series_labels[i] for i in chosen], axis_labels, page_title,
                ticks=ticks, tick_labels=tick_labels, filename=paged_name(filename, page),
                pinned={series_labels[i] for i in pinned_idx},
            ))
        return paths

    def draw_radar(self, values: np.ndarray, series_labels: List[str], axis_labels: List[str],
                   title: str, *, ticks: List[float], tick_labels: List[str], filename: str,
                   pinned: Optional[Set[str]] = None) -> Path:
        """Gambar satu radar (API publik untuk pembuat grafik lain, mis. grafik per grup)."""
        return self._draw_radar(values, series_labels, axis_labels, title, ticks=ticks,
                                tick_labels=tick_labels, filename=filename, pinned=pinned)

    def _draw_radar(self, values: np.ndarray, series_labels: List[str], axis_labels: List[str],
                    title: str, *, ticks: List[float], tick_labels: List[str], filename: str,
                    pinned: Optional[Set[str]] = None) -> Path:
        n_axes = len(axis_labels)
        angles = np.linspace(0, 2 * np.pi, n_axes, endpoint=False).tolist()
        closed = angles + angles[:1]
        pinned = set(pinned or ())

        pinned_styles = ["--", "-.", ":"]        # beberapa ligan pinned (native) tetap bisa dibedakan
        pinned_markers = ["s", "D", "^"]

        with chart_style():
            fig, ax = plt.subplots(figsize=(7.5, 7.0), subplot_kw=dict(polar=True))
            color_index = pin_index = 0
            for row, label in zip(values, series_labels):
                data = row.tolist() + row[:1].tolist()
                if label in pinned:
                    ax.plot(closed, data, marker=pinned_markers[pin_index % 3], markersize=4.0, linewidth=1.9,
                            linestyle=pinned_styles[pin_index % 3], color=COLOR_NATIVE, label=label)
                    ax.fill(closed, data, color=COLOR_NATIVE, alpha=0.06)
                    pin_index += 1
                    continue
                color = PALETTE[color_index % len(PALETTE)]
                color_index += 1
                ax.plot(closed, data, marker="o", markersize=3.5, linewidth=1.6, color=color, label=label)
                ax.fill(closed, data, color=color, alpha=0.08)

            ax.set_xticks(angles)
            ax.set_xticklabels(axis_labels, fontsize=8.5)
            ax.set_ylim(0, 1.0)
            ax.set_yticks(ticks)
            ax.set_yticklabels(tick_labels, fontsize=7, color="#666666")
            ax.set_rlabel_position(180 / n_axes)
            ax.grid(color="#D5D5D5", linewidth=0.6)
            ax.spines["polar"].set_color("#BBBBBB")
            ax.tick_params(axis="x", pad=16)
            ax.set_title(title, pad=22)
            ax.legend(loc="center left", bbox_to_anchor=(1.28, 0.5))
            return self._save(fig, filename)
