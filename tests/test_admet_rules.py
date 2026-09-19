"""Test aturan klasifikasi ADMET: tiap RuleType, kategori, skor kategori, legenda."""

import pytest

from chemflow.admet.admet_rules import (
    CATEGORIES, RULES, Flag, RuleType, category_of, category_scores, classify_admet_value,
    columns_for_category, get_rule, rules_by_category, threshold_text,
)


def test_kolom_tak_dikenal_flag_na():
    assert classify_admet_value("KolomYangTidakAda", 0.5).flag == Flag.NA


def test_nilai_kosong_flag_na():
    assert classify_admet_value("hERG", None).flag == Flag.NA
    assert classify_admet_value("hERG", "bukan angka").flag == Flag.NA
    assert classify_admet_value("hERG", float("nan")).flag == Flag.NA


def test_tiered_batas():
    assert classify_admet_value("hERG", 0.1).flag == Flag.GREEN
    assert classify_admet_value("hERG", 0.5).flag == Flag.YELLOW
    assert classify_admet_value("hERG", 0.9).flag == Flag.RED


def test_tiered_reversed():
    assert classify_admet_value("BCRP", 0.1).flag == Flag.RED
    assert classify_admet_value("BCRP", 0.5).flag == Flag.YELLOW
    assert classify_admet_value("BCRP", 0.9).flag == Flag.GREEN
    assert classify_admet_value("LM-human", 0.9).flag == Flag.GREEN


def test_alert_count_string_dan_angka():
    assert classify_admet_value("PAINS", "['-']").flag == Flag.GREEN
    assert classify_admet_value("PAINS", "[(3, 4, 5)]").flag == Flag.RED
    assert classify_admet_value("Alarm_NMR", 0).flag == Flag.GREEN
    assert classify_admet_value("Alarm_NMR", 2).flag == Flag.RED


def test_threshold_gte_dan_lte():
    assert classify_admet_value("caco2", -4.0).flag == Flag.GREEN
    assert classify_admet_value("caco2", -6.0).flag == Flag.RED
    assert classify_admet_value("PPB", 50.0).flag == Flag.GREEN
    assert classify_admet_value("PPB", 95.0).flag == Flag.RED
    assert classify_admet_value("Lipinski", 0).flag == Flag.GREEN
    assert classify_admet_value("Lipinski", 2).flag == Flag.RED


def test_range():
    assert classify_admet_value("MW", 350).flag == Flag.GREEN
    assert classify_admet_value("MW", 700).flag == Flag.RED
    assert classify_admet_value("VDss", 0.0).flag == Flag.GREEN
    assert classify_admet_value("VDss", 2.0).flag == Flag.RED


def test_alias_logvdss_dikenali():
    assert get_rule("logVDss") is get_rule("VDss")
    assert classify_admet_value("logVDss", 0.0).flag == Flag.GREEN


def test_tiered_range_dua_arah():
    assert classify_admet_value("cl-plasma", 3).flag == Flag.GREEN
    assert classify_admet_value("cl-plasma", 10).flag == Flag.YELLOW
    assert classify_admet_value("cl-plasma", 20).flag == Flag.RED
    assert classify_admet_value("t0.5", 10).flag == Flag.GREEN
    assert classify_admet_value("t0.5", 0.5).flag == Flag.RED


def test_binary_inverted_gasa():
    assert classify_admet_value("gasa", 0).flag == Flag.GREEN
    assert classify_admet_value("gasa", 1).flag == Flag.RED


def test_deskriptif_selalu_info():
    result = classify_admet_value("BCF", 1.5)
    assert result.flag == Flag.INFO
    assert result.value == 1.5


def test_kategori_lengkap_dan_kolom_terdaftar():
    assert len(CATEGORIES) == len(set(CATEGORIES)) == 6
    for column, rule in RULES.items():
        assert rule.category in CATEGORIES
        assert rule.column == column
        assert category_of(column) == rule.category
    assert "hia" in columns_for_category("Absorpsi")
    assert "hERG" in columns_for_category("Toksisitas")
    assert "hERG" not in columns_for_category("Absorpsi")


def test_setiap_rule_bertipe_valid_punya_parameter_ambang():
    for rule in RULES.values():
        if rule.rule_type == RuleType.RANGE:
            assert rule.lo is not None and rule.hi is not None
        if rule.rule_type == RuleType.THRESHOLD_GTE:
            assert rule.lo is not None
        if rule.rule_type == RuleType.THRESHOLD_LTE:
            assert rule.hi is not None
        if rule.rule_type == RuleType.TIERED_RANGE:
            assert rule.breakpoints is not None


def test_category_scores_rata_rata_skor():
    row = {"hia": 0.1, "f20": 0.9, "hERG": 0.5, "smiles": "CCO"}
    scores = category_scores(row)
    assert scores["Absorpsi"] == pytest.approx(0.5)  # (1.0 + 0.0) / 2
    assert scores["Toksisitas"] == pytest.approx(0.5)
    assert "Fisikokimia" not in scores
    assert "Metabolisme" not in scores  # tak ada kolomnya


def test_threshold_text_dan_legenda_semua_rule():
    for category in CATEGORIES:
        for rule in rules_by_category(category):
            assert isinstance(threshold_text(rule), str) and threshold_text(rule)
    assert "hijau" in threshold_text(get_rule("hERG"))
