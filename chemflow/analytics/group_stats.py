"""
Agregasi per grup untuk perbandingan antar-kelompok senyawa.

Fungsi di sini murni (tanpa matplotlib) agar mudah diuji. Grup "Native" berisi
ligan kokristal referensi dan selalu disertakan sebagai pembanding.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np

from chemflow.admet.admet_rules import (
    FLAG_SCORE, Flag, category_scores, classify_admet_value, rules_by_category,
)

NATIVE_GROUP = "Native"
NO_GROUP = "Tanpa Grup"
NATIVE_LABEL = "Native (ref)"


def group_label(group: Optional[str]) -> str:
    """Label grup tampilan; kosong menjadi ``NO_GROUP``."""
    text = (group or "").strip()
    return text or NO_GROUP


def group_order(group_of: Mapping[str, str], *, native_last: bool = False) -> List[str]:
    """Daftar grup unik menurut kemunculan pertama; ``NATIVE_GROUP`` di awal atau akhir."""
    seen: List[str] = []
    for group in group_of.values():
        if group not in seen:
            seen.append(group)
    natives = [g for g in seen if g == NATIVE_GROUP]
    others = [g for g in seen if g != NATIVE_GROUP]
    return others + natives if native_last else natives + others


def best_affinity_per_ligand(stats: Iterable[Mapping[str, Any]]) -> Dict[tuple, float]:
    """``{(ligan, reseptor): affinity_best}`` dari baris statistik replikasi."""
    return {(r["ligand"], r["receptor"]): float(r["affinity_best"])
            for r in stats if r.get("affinity_best") is not None}


def affinities_by_group_receptor(
    stats: Iterable[Mapping[str, Any]], group_of: Mapping[str, str], *, include_native: bool = False,
) -> Dict[str, Dict[str, List[float]]]:
    """``{reseptor: {grup: [ΔG terbaik tiap ligan]}}``; ligan native dikeluarkan kecuali diminta."""
    result: Dict[str, Dict[str, List[float]]] = {}
    for row in stats:
        if row.get("affinity_best") is None:
            continue
        group = group_of.get(row["ligand"], NO_GROUP)
        if group == NATIVE_GROUP and not include_native:
            continue
        result.setdefault(row["receptor"], {}).setdefault(group, []).append(float(row["affinity_best"]))
    return result


def native_affinity_by_receptor(stats: Iterable[Mapping[str, Any]], group_of: Mapping[str, str]) -> Dict[str, float]:
    """ΔG native tiap reseptor (yang terbaik bila ada beberapa)."""
    result: Dict[str, float] = {}
    for row in stats:
        if group_of.get(row["ligand"]) != NATIVE_GROUP or row.get("affinity_best") is None:
            continue
        value = float(row["affinity_best"])
        current = result.get(row["receptor"])
        if current is None or value < current:
            result[row["receptor"]] = value
    return result


def fraction_better_than_native(
    by_receptor: Mapping[str, Mapping[str, Sequence[float]]], native: Mapping[str, float],
) -> Dict[str, Dict[str, float]]:
    """Persentase ligan tiap grup dengan ΔG <= ΔG native pada reseptor yang sama."""
    result: Dict[str, Dict[str, float]] = {}
    for receptor, groups in by_receptor.items():
        reference = native.get(receptor)
        if reference is None:
            continue
        result[receptor] = {
            group: 100.0 * sum(1 for v in values if v <= reference) / len(values)
            for group, values in groups.items() if values
        }
    return result


def flag_scores_by_group(
    admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str], category: str,
) -> Dict[str, Dict[str, float]]:
    """Rata-rata skor klasifikasi (baik 1, sedang 0,5, buruk 0) per grup x parameter satu kategori.

    Returns:
        ``{grup: {label_parameter: rata-rata}}``. Parameter tanpa data di suatu grup dihilangkan
        dari grup itu.
    """
    available = set().union(*(r.keys() for r in admet_rows)) if admet_rows else set()
    rules = [r for r in rules_by_category(category) if r.scored and r.column in available]
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for row in admet_rows:
        group = group_of.get(row["ligand"], NO_GROUP)
        for rule in rules:
            flag = classify_admet_value(rule.column, row.get(rule.column)).flag
            score = FLAG_SCORE.get(flag)
            if score is not None:
                buckets.setdefault(group, {}).setdefault(rule.label, []).append(score)
    return {group: {label: float(np.mean(values)) for label, values in labels.items()}
            for group, labels in buckets.items()}


def flag_counts_by_group(
    admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str], category: str,
) -> Dict[str, Dict[str, List[float]]]:
    """Persentase [baik, sedang, buruk] per grup x parameter satu kategori (untuk bar bertumpuk)."""
    available = set().union(*(r.keys() for r in admet_rows)) if admet_rows else set()
    rules = [r for r in rules_by_category(category) if r.scored and r.column in available]
    flags: Dict[str, Dict[str, List[Any]]] = {}
    for row in admet_rows:
        group = group_of.get(row["ligand"], NO_GROUP)
        for rule in rules:
            flag = classify_admet_value(rule.column, row.get(rule.column)).flag
            if flag in (Flag.GREEN, Flag.YELLOW, Flag.RED):
                flags.setdefault(group, {}).setdefault(rule.label, []).append(flag)
    result: Dict[str, Dict[str, List[float]]] = {}
    for group, labels in flags.items():
        result[group] = {
            label: [100.0 * values.count(f) / len(values) for f in (Flag.GREEN, Flag.YELLOW, Flag.RED)]
            for label, values in labels.items()
        }
    return result


def category_scores_by_group(
    admet_rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str],
) -> Dict[str, Dict[str, float]]:
    """Rata-rata skor kategori ADMET (``category_scores`` per ligan) per grup: ``{grup: {kategori: skor}}``."""
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for row in admet_rows:
        group = group_of.get(row["ligand"], NO_GROUP)
        for category, score in category_scores(dict(row)).items():
            buckets.setdefault(group, {}).setdefault(category, []).append(score)
    return {group: {cat: float(np.mean(v)) for cat, v in cats.items()} for group, cats in buckets.items()}


def property_by_group(
    rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str], prop: str,
) -> Dict[str, List[float]]:
    """Nilai numerik ``prop`` per grup (mis. MW dari baris Lipinski)."""
    result: Dict[str, List[float]] = {}
    for row in rows:
        if row.get(prop) is None:
            continue
        result.setdefault(group_of.get(row["ligand"], NO_GROUP), []).append(float(row[prop]))
    return result


def with_group(rows: Sequence[Mapping[str, Any]], group_of: Mapping[str, str],
               key: str = "ligand") -> List[Dict[str, Any]]:
    """Salinan baris dengan kolom ``group`` tepat setelah kolom ligan."""
    result = []
    for row in rows:
        record: Dict[str, Any] = {}
        for column, value in row.items():
            record[column] = value
            if column == key:
                record["group"] = group_of.get(row[key], NO_GROUP)
        if "group" not in record:
            record = {"group": group_of.get(row.get(key), NO_GROUP), **record}
        result.append(record)
    return result


def add_delta_vs_native(stats: Sequence[Mapping[str, Any]], group_of: Mapping[str, str]) -> List[Dict[str, Any]]:
    """Salinan baris statistik replikasi dengan kolom ``delta_vs_native``.

    Nilainya ``affinity_best`` dikurangi ΔG native pada reseptor yang sama (negatif berarti lebih kuat dari
    native); ``None`` bila reseptor itu tak punya native atau baris itu sendiri adalah native.
    """
    native = native_affinity_by_receptor(stats, group_of)
    rows: List[Dict[str, Any]] = []
    for row in stats:
        record = dict(row)
        reference = native.get(row["receptor"])
        is_native = group_of.get(row["ligand"]) == NATIVE_GROUP
        if reference is None or is_native or row.get("affinity_best") is None:
            record["delta_vs_native"] = None
        else:
            record["delta_vs_native"] = round(float(row["affinity_best"]) - reference, 3)
        rows.append(record)
    return rows


def summarize_groups(
    lipinski_rows: Sequence[Mapping[str, Any]], admet_rows: Sequence[Mapping[str, Any]],
    group_of: Mapping[str, str],
) -> List[Dict[str, Any]]:
    """Ringkasan per grup: jumlah ligan, rata-rata sifat fisikokimia, % lolos Ro5, skor kategori ADMET."""
    scores = category_scores_by_group(admet_rows, group_of)
    rows: List[Dict[str, Any]] = []
    for group in group_order(group_of):
        record: Dict[str, Any] = {"grup": group, "n_ligan": sum(1 for g in group_of.values() if g == group)}
        members = [r for r in lipinski_rows if group_of.get(r["ligand"]) == group]
        if members:
            record["lolos_Ro5_persen"] = round(100.0 * sum(1 for r in members if r.get("Lolos_Ro5")) / len(members), 1)
            for prop in ("MW", "LogP", "HBD", "HBA"):
                values = [float(r[prop]) for r in members if r.get(prop) is not None]
                if values:
                    record[f"{prop}_rata2"] = round(float(np.mean(values)), 2)
        for category, score in scores.get(group, {}).items():
            record[f"ADMET_{category}"] = round(score, 3)
        rows.append(record)
    return rows


def summarize_docking_by_group(
    stats: Sequence[Mapping[str, Any]], group_of: Mapping[str, str],
) -> List[Dict[str, Any]]:
    """ΔG per reseptor x grup: n, rata-rata, SD, terbaik, ΔG native, dan % ligan yang lebih baik dari native."""
    by_receptor = affinities_by_group_receptor(stats, group_of, include_native=True)
    native = native_affinity_by_receptor(stats, group_of)
    better = fraction_better_than_native(by_receptor, native)
    rows: List[Dict[str, Any]] = []
    for receptor in sorted(by_receptor):
        for group in group_order({g: g for g in by_receptor[receptor]}):
            values = np.array(by_receptor[receptor][group])
            record: Dict[str, Any] = {
                "reseptor": receptor, "grup": group, "n_ligan": int(len(values)),
                "dG_rata2": round(float(values.mean()), 3),
                "dG_sd": round(float(values.std()), 3) if len(values) > 1 else 0.0,
                "dG_terbaik": round(float(values.min()), 3),
                "dG_native": native.get(receptor),
            }
            if group != NATIVE_GROUP and receptor in better:
                record["lebih_baik_dari_native_persen"] = round(better[receptor].get(group, 0.0), 1)
            rows.append(record)
    return rows
