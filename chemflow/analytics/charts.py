"""
Grafik utama hasil chemflow: bar afinitas, radar gabungan, radar per kategori
ADMET, dan bar klasifikasi ADMET.

Semua grafik memakai gaya bersama ``analytics.style`` (palet aman buta warna,
300 dpi) dan ditulis sebagai PNG, dengan format vektor tambahan opsional.
Radar gabungan menormalisasi tiap kriteria min-max lintas ligan yang
dibandingkan; radar ADMET memakai skor klasifikasi (baik 1, sedang 0,5,
buruk 0) sehingga parameter berbeda satuan tetap sebanding.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from chemflow.admet.admet_rules import (
    CAT_PHYSICOCHEMICAL, CATEGORIES, FLAG_SCORE, Flag, classify_admet_value, rules_by_category,
)
from chemflow.analytics.style import (
    COLOR_GOOD, COLOR_MEDIUM, COLOR_POOR, FIG_DPI, PALETTE, chart_style, clean_axes, save_figure,
)


def _wrap(text: str, width: int = 18) -> str:
    return textwrap.fill(str(text), width=width, break_long_words=False)


class ChartBuilder:
    """Pembuat grafik bar dan radar untuk hasil pipeline chemflow."""

    def __init__(self, output_dir: "str | Path", dpi: int = FIG_DPI, formats: Sequence[str] = ("png",),
                 logger: Optional[logging.Logger] = None) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dpi = dpi
        self._formats = tuple(formats)
        self._log = logger or logging.getLogger(__name__)

    def _save(self, fig, filename: str) -> Path:
        path = save_figure(fig, self._dir / filename, dpi=self._dpi, formats=self._formats)
        self._log.debug(f"Grafik tersimpan: {path.name}")
        return path

    def bar_affinity(self, rows: List[Dict[str, Any]], *, ligand_key: str = "ligand",
                     value_key: str = "affinity_best", title: str = "Afinitas Docking Terbaik",
                     top_n: Optional[int] = None, filename: str = "bar_affinity.png") -> Path:
        """Bar horizontal afinitas per ligan (lebih negatif berarti ikatan lebih kuat).

        Args:
            rows: daftar dict berisi ``ligand_key`` dan ``value_key``.
            ligand_key, value_key: nama field di setiap dict.
            title: judul grafik.
            top_n: batasi ke N afinitas terbaik; None berarti semua.
            filename: nama file PNG keluaran.

        Returns:
            Path file PNG yang ditulis.
        """
        data = sorted(rows, key=lambda r: r[value_key])
        if top_n:
            data = data[:top_n]
        labels = [str(r[ligand_key]) for r in data]
        values = np.array([float(r[value_key]) for r in data])

        with chart_style():
            fig, ax = plt.subplots(figsize=(8.0, max(3.2, 0.32 * len(labels) + 1.4)))
            colors = [PALETTE[0] if v < 0 else PALETTE[1] for v in values]
            ypos = np.arange(len(labels))
            ax.barh(ypos, values, color=colors, height=0.72, edgecolor="none")
            ax.set_yticks(ypos)
            ax.set_yticklabels(labels)
            ax.invert_yaxis()
            ax.axvline(0, color="#444444", linewidth=0.8)
            ax.set_xlabel("Afinitas docking (kcal/mol)")
            ax.set_title(title)
            clean_axes(ax, grid_axis="x")

            span = max(1.0, float(np.abs(values).max()))
            ax.set_xlim(min(0.0, values.min()) - 0.14 * span, max(0.0, values.max()) + 0.06 * span)
            for y, v in zip(ypos, values):
                ax.annotate(f"{v:.2f}", (v, y), xytext=(-4 if v < 0 else 4, 0), textcoords="offset points",
                            ha="right" if v < 0 else "left", va="center", fontsize=8, color="#222222")
            return self._save(fig, filename)

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
        top_n: int = 6,
        rank_by: Optional[str] = None,
        filename: str = "radar_combined.png",
    ) -> Optional[Path]:
        """Radar multi-kriteria (afinitas, fisikokimia, skor kategori ADMET).

        Kriteria dinormalisasi 0-1 (min-max lintas ligan) supaya satuan yang
        berbeda tetap sebanding pada satu radar, kecuali kriteria pada
        ``absolute`` yang sudah berskala 0-1 dan dipakai apa adanya.

        Args:
            ligand_rows: daftar dict, satu per ligan, berisi ``criteria`` dan ``label_key``.
            criteria: nama field yang menjadi sumbu radar.
            label_key: field nama pada legenda.
            title: judul grafik.
            lower_is_better: subset ``criteria`` yang nilai kecilnya lebih baik
                (dibalik supaya arah baik selalu ke luar).
            absolute: subset ``criteria`` yang sudah berskala 0-1 (tanpa min-max).
            criteria_labels: nama tampilan tiap kriteria pada sumbu.
            top_n: jumlah ligan teratas yang digambar.
            rank_by: kriteria penentu peringkat; ``None`` memakai skor komposit
                (rata-rata seluruh kriteria ternormalisasi).
            filename: nama file PNG keluaran.

        Returns:
            Path PNG, atau ``None`` jika tak ada ligan dengan data lengkap.
        """
        lower_is_better = set(lower_is_better or [])
        absolute = set(absolute or [])
        labels_map = criteria_labels or {}

        valid_rows = [r for r in ligand_rows if all(r.get(c) is not None for c in criteria)]
        if not valid_rows or len(criteria) < 3:
            self._log.warning("Radar gabungan dilewati: data lengkap atau jumlah kriteria (minimal 3) tidak cukup.")
            return None

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
        order = np.argsort(-ranking, kind="stable")[:top_n]
        if len(valid_rows) > top_n:
            basis = labels_map.get(rank_by, rank_by) if ranked_by_criterion else "skor komposit"
            title += f"\n{top_n} dari {len(valid_rows)} ligan dengan {basis} terbaik"
        axis_labels = [_wrap(labels_map.get(c, c), 14) for c in criteria]
        return self._draw_radar(
            normalized[order], [str(valid_rows[i][label_key]) for i in order], axis_labels, title,
            ticks=[0.25, 0.5, 0.75, 1.0], tick_labels=["0,25", "0,5", "0,75", "1,0"], filename=filename,
        )

    def radar_by_category(self, admet_rows: List[Dict[str, Any]], category: str, *,
                          label_key: str = "ligand", top_n: int = 8, max_axes: int = 12,
                          filename: Optional[str] = None) -> Optional[Path]:
        """Radar profil ADMET satu kategori: sumbu = parameter, garis = ligan.

        Tiap nilai diubah ke skor klasifikasi (baik 1, sedang 0,5, buruk 0);
        nilai tanpa data memakai 0,5 agar poligon tetap tertutup. Ligan
        diurutkan menurut rata-rata skor seluruh parameter kategori dan
        ``top_n`` teratas digambar. Jika parameter melebihi ``max_axes``,
        sumbu dibatasi ke parameter dengan variasi skor terbesar antar ligan
        supaya radar tetap terbaca (rincian lengkap ada di bar klasifikasi).

        Returns:
            Path PNG, atau ``None`` jika kurang dari 3 parameter terskor
            tersedia pada data (radar butuh minimal 3 sumbu).
        """
        if not admet_rows:
            return None
        available = set().union(*(r.keys() for r in admet_rows))
        rules = [r for r in rules_by_category(category) if r.scored and r.column in available]
        if len(rules) < 3:
            self._log.info(f"Radar ADMET '{category}' dilewati: kurang dari 3 parameter terskor tersedia.")
            return None

        scores = []
        for row in admet_rows:
            scores.append([
                FLAG_SCORE.get(classify_admet_value(rule.column, row.get(rule.column)).flag, 0.5)
                for rule in rules
            ])
        scores = np.array(scores)
        order = np.argsort(-scores.mean(axis=1), kind="stable")[:top_n]

        notes = []
        if len(rules) > max_axes:
            keep = sorted(np.argsort(-scores.var(axis=0), kind="stable")[:max_axes])
            notes.append(f"{max_axes} dari {len(rules)} parameter dengan variasi terbesar")
            rules = [rules[i] for i in keep]
            scores = scores[:, keep]
        if len(admet_rows) > top_n:
            notes.append(f"{top_n} dari {len(admet_rows)} ligan dengan skor tertinggi")
        title = f"Profil ADMET: {category}" + ("\n" + ", ".join(notes) if notes else "")

        return self._draw_radar(
            scores[order], [str(admet_rows[i][label_key]) for i in order],
            [_wrap(r.label, 14) for r in rules], title,
            ticks=[0.0, 0.5, 1.0], tick_labels=["Buruk", "Sedang", "Baik"],
            filename=filename or f"radar_admet_{category.lower()}.png",
        )

    def radar_all_admet_categories(self, admet_rows: List[Dict[str, Any]], *,
                                   label_key: str = "ligand", top_n: int = 8) -> List[Path]:
        """Satu radar per kategori ADMET (kecuali Fisikokimia) yang punya cukup parameter."""
        paths = []
        for category in CATEGORIES:
            if category == CAT_PHYSICOCHEMICAL:
                continue
            path = self.radar_by_category(admet_rows, category, label_key=label_key, top_n=top_n)
            if path is not None:
                paths.append(path)
        return paths

    def admet_stacked_bar(self, admet_rows: List[Dict[str, Any]], category: str,
                          filename: Optional[str] = None) -> Optional[Path]:
        """Bar bertumpuk 100%: persentase ligan baik/sedang/buruk untuk tiap parameter kategori.

        Returns:
            Path PNG, atau ``None`` jika tak ada parameter terskor pada data.
        """
        if not admet_rows:
            return None
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
            return None

        data = np.array(shares)
        with chart_style():
            fig, ax = plt.subplots(figsize=(8.0, max(3.0, 0.3 * len(labels) + 1.8)))
            ypos = np.arange(len(labels))
            left = np.zeros(len(labels))
            for column, color, name in zip(data.T, (COLOR_GOOD, COLOR_MEDIUM, COLOR_POOR), ("Baik", "Sedang", "Buruk")):
                ax.barh(ypos, column, left=left, color=color, label=name, height=0.72, edgecolor="white", linewidth=0.5)
                left += column
            ax.set_yticks(ypos)
            ax.set_yticklabels(labels)
            ax.invert_yaxis()
            ax.set_xlim(0, 100)
            ax.set_xlabel("Persentase ligan (%)")
            ax.set_title(f"Klasifikasi ADMET: {category}")
            clean_axes(ax)
            ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
            return self._save(fig, filename or f"admet_klasifikasi_{category.lower()}.png")

    def admet_all_stacked_bars(self, admet_rows: List[Dict[str, Any]]) -> List[Path]:
        paths = []
        for category in CATEGORIES:
            path = self.admet_stacked_bar(admet_rows, category)
            if path is not None:
                paths.append(path)
        return paths

    def _draw_radar(self, values: np.ndarray, series_labels: List[str], axis_labels: List[str],
                    title: str, *, ticks: List[float], tick_labels: List[str], filename: str) -> Path:
        n_axes = len(axis_labels)
        angles = np.linspace(0, 2 * np.pi, n_axes, endpoint=False).tolist()
        closed = angles + angles[:1]

        with chart_style():
            fig, ax = plt.subplots(figsize=(7.5, 7.0), subplot_kw=dict(polar=True))
            for idx, (row, label) in enumerate(zip(values, series_labels)):
                data = row.tolist() + row[:1].tolist()
                color = PALETTE[idx % len(PALETTE)]
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
            ax.legend(loc="center left", bbox_to_anchor=(1.10, 0.5))
            return self._save(fig, filename)
