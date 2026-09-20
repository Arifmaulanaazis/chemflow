"""
Grafik perbandingan antar-grup senyawa: ADMET, ΔG docking, dan sifat fisikokimia
per grup, dengan ligan native (grup "Native") sebagai pembanding.

Grafik membandingkan ADMET, ΔG docking, atau sifat fisikokimia antar-grup. Ligan
yang sama di beberapa grup dihitung di tiap grup sesuai keanggotaannya. Grafik
yang memuat banyak grup, reseptor, atau parameter dipotong otomatis menjadi
beberapa bagian (``_part01of03``), dengan skala yang dihitung dari seluruh data.
Semua metode mengembalikan ``List[Path]``.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from chemflow.admet.admet_rules import (
    CAT_PHYSICOCHEMICAL, CATEGORIES, category_scores, rules_by_category,
)
from chemflow.analytics.charts import ChartBuilder, _wrap
from chemflow.analytics.group_stats import (
    NATIVE_GROUP, NATIVE_LABEL, NO_GROUP, affinities_by_group_receptor, category_scores_by_group,
    flag_counts_by_group, flag_scores_by_group, fraction_better_than_native, group_order,
    native_affinity_by_receptor, property_by_group,
)
from chemflow.analytics.heatmap import HeatmapBuilder
from chemflow.analytics.paging import paged_name, paginate, paginate_grid
from chemflow.analytics.style import (
    COLOR_GOOD, COLOR_MEDIUM, COLOR_NATIVE, COLOR_POOR, DEFAULT_MAX_COLS, DEFAULT_MAX_ROWS, FIG_DPI,
    MAX_RADAR_SERIES, chart_style, clean_axes, group_colors, save_figure,
)

_PANELS_PER_PAGE = 6          # panel reseptor per gambar
_PANELS_PER_ROW = 3
_STACKED_PANELS_PER_PAGE = 4  # panel grup per gambar bar bertumpuk
_ADMET_CMAP = LinearSegmentedColormap.from_list("admet", [COLOR_POOR, COLOR_MEDIUM, COLOR_GOOD])


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")


class GroupChartBuilder:
    """Pembuat grafik per grup untuk hasil pipeline chemflow."""

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
        self._charts = ChartBuilder(self._dir, dpi=dpi, formats=formats, logger=self._log, max_rows=max_rows)
        self._heatmaps = HeatmapBuilder(self._dir, dpi=dpi, formats=formats, logger=self._log,
                                        max_rows=max_rows, max_cols=max_cols)

    def _save(self, fig, filename: str) -> Path:
        path = save_figure(fig, self._dir / filename, dpi=self._dpi, formats=self._formats)
        self._log.debug(f"Grafik grup tersimpan: {path.name}")
        return path

    def plot_all(self, replicate_stats: Sequence[Mapping[str, Any]], lipinski_rows: Sequence[Mapping[str, Any]],
                 admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str]) -> List[Path]:
        """Buat seluruh grafik per grup yang datanya tersedia; grafik tanpa data dilewati."""
        groups = set(group_of.values())
        if len(groups) < 2:
            self._log.info(
                "Grafik per grup dilewati: hanya satu grup terdeteksi. Tambahkan grup lain di Excel ligan "
                "atau aktifkan ligan native untuk pembanding."
            )
            return []

        paths: List[Path] = []
        steps = (
            ("ΔG per grup (box)", self.affinity_box, (replicate_stats, group_of)),
            ("ΔG per grup (heatmap)", self.affinity_heatmaps, (replicate_stats, group_of)),
            ("ADMET per grup (heatmap)", self.admet_heatmaps, (admet_rows, group_of)),
            ("ADMET per grup (radar)", self.admet_radars, (admet_rows, group_of)),
            ("ADMET per grup (klasifikasi)", self.admet_stacked, (admet_rows, group_of)),
            ("Fisikokimia per grup", self.physchem_box, (lipinski_rows, group_of)),
            ("Profil gabungan per grup", self.combined_radar, (replicate_stats, lipinski_rows, admet_rows, group_of)),
        )
        for label, method, args in steps:
            try:
                paths.extend(method(*args))
            except Exception as exc:
                self._log.warning(f"Grafik '{label}' dilewati: {exc}")
                self._log.debug("Detail error:", exc_info=True)
        self._log.info(f"Grafik per grup: {len(paths)} gambar.")
        return paths

    def affinity_box(self, stats: Sequence[Mapping[str, Any]], group_of: Mapping[str, str],
                     filename: str = "grup_afinitas_box.png") -> List[Path]:
        """Sebaran ΔG terbaik tiap ligan per grup, satu panel per reseptor; garis putus-putus = ΔG native."""
        by_receptor = affinities_by_group_receptor(stats, group_of)
        if not by_receptor:
            return []
        native = native_affinity_by_receptor(stats, group_of)
        receptors = sorted(by_receptor)
        pooled: Dict[str, List[float]] = {}
        for groups in by_receptor.values():
            for group, values in groups.items():
                pooled.setdefault(group, []).extend(values)
        groups_sorted = sorted(pooled, key=lambda g: float(np.median(pooled[g])))
        colors = group_colors(group_order(group_of))
        rng = np.random.default_rng(0)

        paths: List[Path] = []
        for tile in paginate_grid(len(receptors), len(groups_sorted), _PANELS_PER_PAGE, self._max_cols):
            page_receptors = receptors[tile.rows.start:tile.rows.stop]
            page_groups = groups_sorted[tile.cols.start:tile.cols.stop]
            n_cols = min(_PANELS_PER_ROW, len(page_receptors))
            n_rows = math.ceil(len(page_receptors) / n_cols)
            width = max(4.2, 0.55 * len(page_groups) + 2.2)
            with chart_style():
                fig, axes = plt.subplots(n_rows, n_cols, figsize=(width * n_cols, 3.8 * n_rows + 0.6),
                                         squeeze=False)
                for k, receptor in enumerate(page_receptors):
                    ax = axes[k // n_cols][k % n_cols]
                    self._box_panel(ax, by_receptor[receptor], page_groups, colors, rng)
                    ax.set_title(receptor, fontsize=10)
                    if k % n_cols == 0:
                        ax.set_ylabel("ΔG (kcal/mol)")
                    reference = native.get(receptor)
                    if reference is not None:
                        ax.axhline(reference, color=COLOR_NATIVE, linestyle="--", linewidth=1.3, zorder=1)
                        ax.annotate(f"Native {reference:.2f}", (1.0, reference), xycoords=("axes fraction", "data"),
                                    xytext=(-3, 3), textcoords="offset points", ha="right", va="bottom",
                                    fontsize=7.5, color=COLOR_NATIVE)
                    clean_axes(ax, grid_axis="y")
                for k in range(len(page_receptors), n_rows * n_cols):
                    axes[k // n_cols][k % n_cols].axis("off")
                fig.suptitle("ΔG Docking per Grup (lebih negatif = lebih kuat)" + tile.title_suffix)
                fig.tight_layout()
                paths.append(self._save(fig, paged_name(filename, tile)))
        return paths

    def affinity_heatmaps(self, stats: Sequence[Mapping[str, Any]], group_of: Mapping[str, str]) -> List[Path]:
        """Heatmap reseptor x grup: ΔG rata-rata (dengan kolom Native) dan % ligan yang ΔG-nya ≤ native."""
        by_receptor = affinities_by_group_receptor(stats, group_of)
        if not by_receptor:
            return []
        native = native_affinity_by_receptor(stats, group_of)
        receptors = sorted(by_receptor)
        groups = [g for g in group_order(group_of) if g != NATIVE_GROUP
                  and any(g in by_receptor[r] for r in receptors)]
        counts = {g: max(len(by_receptor[r].get(g, [])) for r in receptors) for g in groups}
        labels = [f"{g}\n(n={counts[g]})" for g in groups]

        offset = 1 if native else 0
        matrix = np.full((len(receptors), len(groups) + offset), np.nan)
        for i, receptor in enumerate(receptors):
            for j, group in enumerate(groups):
                values = by_receptor[receptor].get(group)
                if values:
                    matrix[i, j + offset] = float(np.mean(values))
            if native and receptor in native:
                matrix[i, 0] = native[receptor]
        columns = ([NATIVE_LABEL] if native else []) + labels

        paths = self._heatmaps.heatmap_matrix(
            matrix, receptors, columns, "grup_heatmap_afinitas.png",
            title="ΔG Rata-rata per Grup (Reseptor x Grup)", cbar_label="ΔG rata-rata (kcal/mol)",
            cmap="viridis_r", pinned_cols=[0] if native else (),
        )

        better = fraction_better_than_native(by_receptor, native)
        if better:
            share = np.full((len(receptors), len(groups)), np.nan)
            for i, receptor in enumerate(receptors):
                for j, group in enumerate(groups):
                    if receptor in better and group in better[receptor]:
                        share[i, j] = better[receptor][group]
            paths += self._heatmaps.heatmap_matrix(
                share, receptors, labels, "grup_heatmap_lebih_baik_dari_native.png",
                title="Ligan dengan ΔG ≤ Native (per Grup)", cbar_label="Ligan lebih baik dari native (%)",
                cmap="YlGn", vmin=0.0, vmax=100.0, annotation_fmt=lambda v: f"{v:.0f}",
            )
        return paths

    def admet_heatmaps(self, admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str]) -> List[Path]:
        """Heatmap grup x parameter per kategori ADMET dan ringkasan grup x kategori (nilai = skor 0-1)."""
        if not admet_rows:
            return []
        groups = [g for g in group_order(group_of) if any(group_of.get(r["ligand"]) == g for r in admet_rows)]
        ticks, tick_labels = [0.0, 0.5, 1.0], ["Buruk", "Sedang", "Baik"]
        paths: List[Path] = []

        summary = category_scores_by_group(admet_rows, group_of)
        categories = [c for c in CATEGORIES if c != CAT_PHYSICOCHEMICAL
                      and any(c in summary.get(g, {}) for g in groups)]
        if categories:
            matrix = np.array([[summary.get(g, {}).get(c, np.nan) for c in categories] for g in groups])
            paths += self._heatmaps.heatmap_matrix(
                matrix, groups, categories, "grup_admet_ringkasan.png",
                title="Skor ADMET per Kategori dan Grup", cbar_label="Skor rata-rata (0-1)",
                cmap=_ADMET_CMAP, vmin=0.0, vmax=1.0, cbar_ticks=ticks, cbar_ticklabels=tick_labels,
                row_groups={g: g for g in groups},
            )

        for category in CATEGORIES:
            scores = flag_scores_by_group(admet_rows, group_of, category)
            parameters = [r.label for r in rules_by_category(category)
                          if any(r.label in scores.get(g, {}) for g in groups)]
            if not parameters:
                continue
            matrix = np.array([[scores.get(g, {}).get(p, np.nan) for p in parameters] for g in groups])
            paths += self._heatmaps.heatmap_matrix(
                matrix, groups, parameters, f"grup_admet_heatmap_{_safe_name(category)}.png",
                title=f"Skor ADMET per Parameter dan Grup: {category}", cbar_label="Skor rata-rata (0-1)",
                cmap=_ADMET_CMAP, vmin=0.0, vmax=1.0, cbar_ticks=ticks, cbar_ticklabels=tick_labels,
                row_groups={g: g for g in groups},
            )
        return paths

    def admet_radars(self, admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str],
                     max_axes: int = 12) -> List[Path]:
        """Radar per kategori ADMET: sumbu = parameter, garis = grup (rata-rata skor), Native disematkan."""
        if not admet_rows:
            return []
        groups = [g for g in group_order(group_of) if any(group_of.get(r["ligand"]) == g for r in admet_rows)]
        paths: List[Path] = []
        for category in CATEGORIES:
            if category == CAT_PHYSICOCHEMICAL:
                continue
            scores = flag_scores_by_group(admet_rows, group_of, category)
            parameters = [r.label for r in rules_by_category(category)
                          if any(r.label in scores.get(g, {}) for g in groups)]
            if len(parameters) < 3:
                continue
            values = np.array([[scores.get(g, {}).get(p, 0.5) for p in parameters] for g in groups])

            title = f"Profil ADMET per Grup: {category}"
            if len(parameters) > max_axes:
                keep = sorted(np.argsort(-values.var(axis=0), kind="stable")[:max_axes])
                title += f"\n{max_axes} dari {len(parameters)} parameter dengan variasi terbesar antar grup"
                parameters = [parameters[i] for i in keep]
                values = values[:, keep]
            order = [int(i) for i in np.argsort(-values.mean(axis=1), kind="stable")]
            paths += self._charts.radar_pages(
                values, groups, order, [_wrap(p, 14) for p in parameters], title, "skor rata-rata",
                ticks=[0.0, 0.5, 1.0], tick_labels=["Buruk", "Sedang", "Baik"],
                filename=f"grup_admet_radar_{_safe_name(category)}.png", per_page=MAX_RADAR_SERIES,
                pinned={NATIVE_GROUP}, max_pages=5, noun="grup",
            )
        return paths

    def admet_stacked(self, admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str]) -> List[Path]:
        """Bar bertumpuk baik/sedang/buruk per parameter, satu panel per grup (y bersama agar mudah dibandingkan)."""
        if not admet_rows:
            return []
        groups = [g for g in group_order(group_of) if any(group_of.get(r["ligand"]) == g for r in admet_rows)]
        paths: List[Path] = []
        for category in CATEGORIES:
            shares = flag_counts_by_group(admet_rows, group_of, category)
            parameters = [r.label for r in rules_by_category(category)
                          if any(r.label in shares.get(g, {}) for g in groups)]
            if not parameters:
                continue
            filename = f"grup_admet_klasifikasi_{_safe_name(category)}.png"
            for tile in paginate_grid(len(parameters), len(groups), self._max_rows, _STACKED_PANELS_PER_PAGE):
                page_params = parameters[tile.rows.start:tile.rows.stop]
                page_groups = groups[tile.cols.start:tile.cols.stop]
                with chart_style():
                    fig, axes = plt.subplots(
                        1, len(page_groups), sharey=True, squeeze=False,
                        figsize=(max(5.0, 3.2 * len(page_groups) + 2.0), max(3.2, 0.32 * len(page_params) + 2.2)),
                    )
                    ypos = np.arange(len(page_params))
                    for ax, group in zip(axes[0], page_groups):
                        left = np.zeros(len(page_params))
                        for k, (color, name) in enumerate(((COLOR_GOOD, "Baik"), (COLOR_MEDIUM, "Sedang"),
                                                           (COLOR_POOR, "Buruk"))):
                            column = np.array([shares.get(group, {}).get(p, [0.0, 0.0, 0.0])[k]
                                               for p in page_params])
                            ax.barh(ypos, column, left=left, color=color, height=0.72, edgecolor="white",
                                    linewidth=0.5, label=name)
                            left += column
                        ax.set_xlim(0, 100)
                        ax.set_title(group, fontsize=10)
                        ax.set_xlabel("Persentase ligan (%)")
                        clean_axes(ax)
                    axes[0][0].set_yticks(ypos)
                    axes[0][0].set_yticklabels(page_params)
                    axes[0][0].invert_yaxis()
                    fig.legend(handles=[Patch(color=c, label=n) for c, n in
                                        ((COLOR_GOOD, "Baik"), (COLOR_MEDIUM, "Sedang"), (COLOR_POOR, "Buruk"))],
                               loc="lower center", ncol=3, frameon=False)
                    fig.suptitle(f"Klasifikasi ADMET per Grup: {category}{tile.title_suffix}")
                    fig.tight_layout(rect=(0, 0.06, 1, 1))
                    paths.append(self._save(fig, paged_name(filename, tile)))
        return paths

    def physchem_box(self, lipinski_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str],
                     properties: Sequence[str] = ("MW", "LogP", "HBD", "HBA"),
                     filename: str = "grup_fisikokimia_box.png") -> List[Path]:
        """Sebaran MW, LogP, HBD, HBA per grup (Native ikut sebagai grup pembanding)."""
        if not lipinski_rows:
            return []
        groups = [g for g in group_order(group_of) if any(group_of.get(r["ligand"]) == g for r in lipinski_rows)]
        if not groups:
            return []
        colors = group_colors(group_order(group_of))
        data = {prop: property_by_group(lipinski_rows, group_of, prop) for prop in properties}
        rng = np.random.default_rng(0)

        paths: List[Path] = []
        for page in paginate(len(groups), self._max_cols):
            page_groups = page.slice(groups)
            n_cols = 2
            n_rows = math.ceil(len(properties) / n_cols)
            width = max(4.4, 0.6 * len(page_groups) + 2.4)
            with chart_style():
                fig, axes = plt.subplots(n_rows, n_cols, figsize=(width * n_cols, 3.8 * n_rows + 0.6),
                                         squeeze=False)
                for k, prop in enumerate(properties):
                    ax = axes[k // n_cols][k % n_cols]
                    self._box_panel(ax, data[prop], page_groups, colors, rng)
                    ax.set_title(prop, fontsize=10)
                    clean_axes(ax, grid_axis="y")
                for k in range(len(properties), n_rows * n_cols):
                    axes[k // n_cols][k % n_cols].axis("off")
                fig.suptitle("Sifat Fisikokimia per Grup" + page.title_suffix)
                fig.tight_layout()
                paths.append(self._save(fig, paged_name(filename, page)))
        return paths

    def combined_radar(self, stats: Sequence[Mapping[str, Any]], lipinski_rows: Sequence[Mapping[str, Any]],
                       admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str],
                       filename: str = "grup_radar_gabungan.png") -> List[Path]:
        """Radar gabungan (ΔG, fisikokimia, skor ADMET): satu garis per grup = rata-rata anggotanya."""
        best_affinity: Dict[str, float] = {}
        for row in stats:
            if row.get("affinity_best") is None:
                continue
            current = best_affinity.get(row["ligand"])
            if current is None or row["affinity_best"] < current:
                best_affinity[row["ligand"]] = float(row["affinity_best"])
        if not best_affinity:
            return []

        lipinski = {r["ligand"]: r for r in lipinski_rows}
        admet = {r["ligand"]: category_scores(dict(r)) for r in admet_rows}
        criteria = ["affinity_best"]
        labels = {"affinity_best": "ΔG docking"}
        if lipinski:
            criteria += ["MW", "LogP", "HBD", "HBA"]
        admet_criteria = sorted({k for scores in admet.values() for k in scores},
                                key=lambda c: list(CATEGORIES).index(c))
        criteria += admet_criteria
        labels.update({c: f"ADMET {c}" for c in admet_criteria})

        buckets: Dict[str, Dict[str, List[float]]] = {}
        for ligand, affinity in best_affinity.items():
            group = group_of.get(ligand, NO_GROUP)
            record: Dict[str, Any] = {"affinity_best": affinity}
            record.update({p: lipinski[ligand][p] for p in ("MW", "LogP", "HBD", "HBA")
                           if ligand in lipinski and lipinski[ligand].get(p) is not None})
            record.update(admet.get(ligand, {}))
            for criterion in criteria:
                if criterion in record:
                    buckets.setdefault(group, {}).setdefault(criterion, []).append(float(record[criterion]))

        rows = []
        for group, values in buckets.items():
            if all(c in values for c in criteria):
                rows.append({"grup": group, **{c: float(np.mean(values[c])) for c in criteria}})
        if len(rows) < 2:
            return []

        title = "Profil Gabungan per Grup: " + " + ".join(
            (["Fisikokimia"] if lipinski else []) + (["ADMET"] if admet_criteria else []) + ["ΔG"]
        )
        return self._charts.radar_combined(
            rows, criteria=criteria, label_key="grup", title=title,
            lower_is_better=[c for c in ("affinity_best", "MW", "LogP", "HBD", "HBA") if c in criteria],
            absolute=admet_criteria, criteria_labels=labels, rank_by="affinity_best", filename=filename,
            pinned={NATIVE_GROUP},
        )

    @staticmethod
    def _box_panel(ax, values_by_group: Mapping[str, Sequence[float]], order: Sequence[str],
                   colors: Mapping[str, str], rng: np.random.Generator) -> None:
        """Box plot + titik per grup pada satu sumbu; grup tanpa data dibiarkan kosong."""
        positions = list(range(len(order)))
        filled = [(p, list(values_by_group.get(g, []))) for p, g in zip(positions, order)]
        filled = [(p, v) for p, v in filled if v]
        if filled:
            box = ax.boxplot([v for _, v in filled], positions=[p for p, _ in filled], widths=0.55,
                             patch_artist=True, showfliers=False, medianprops=dict(color="#222222", linewidth=1.4))
            for patch, (position, _) in zip(box["boxes"], filled):
                color = colors.get(order[position], "#999999")
                patch.set_facecolor(color)
                patch.set_alpha(0.3)
                patch.set_edgecolor(color)
            for position, values in filled:
                color = colors.get(order[position], "#999999")
                ax.scatter(position + rng.uniform(-0.16, 0.16, len(values)), values, s=15, color=color,
                           alpha=0.9, edgecolors="white", linewidths=0.4, zorder=3)
        ax.set_xticks(positions)
        ax.set_xticklabels([f"{_wrap(g, 14)}\n(n={len(values_by_group.get(g, []))})" for g in order],
                           rotation=45, ha="right", fontsize=8)
        ax.set_xlim(-0.6, len(order) - 0.4)
