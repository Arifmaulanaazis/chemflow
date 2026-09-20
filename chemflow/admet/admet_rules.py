"""
Aturan klasifikasi nilai ADMET (pewarnaan sel Excel dan grafik ADMET).

Satu tabel ``RULES`` menjadi sumber tunggal nama kolom, kategori, satuan,
dan ambang batas untuk seluruh keluaran ADMETLab3 (kolom CSV persis seperti
header aslinya). Setiap nilai diklasifikasikan ke ``Flag.GREEN`` (baik),
``Flag.YELLOW`` (sedang), ``Flag.RED`` (buruk), ``Flag.NA`` (tidak ada
nilai), atau ``Flag.INFO`` (parameter deskriptif tanpa ambang).

Kolom yang tidak ada di ``RULES`` diperlakukan ``Flag.NA`` tanpa error,
sehingga perubahan penamaan kolom di sisi ADMETLab3 tidak menggagalkan
ekspor; cukup tambahkan atau sesuaikan entri sesuai header CSV terbaru.

Ambang mengikuti dokumentasi ADMETLab3 (Fu et al. 2024, Nucleic Acids
Research 52(W1):W422-W431; admetlab3.scbdd.com). Kolom probabilitas memakai pita 0-0,3 /
0,3-0,7 / 0,7-1,0.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class Flag(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    NA = "na"
    INFO = "info"


class RuleType(str, Enum):
    RANGE = "range"
    THRESHOLD_GTE = "threshold_gte"
    THRESHOLD_LTE = "threshold_lte"
    TIERED = "tiered"
    TIERED_REVERSED = "tiered_reversed"
    TIERED_RANGE = "tiered_range"
    ALERT_COUNT = "alert_count"
    BINARY = "binary"
    DESCRIPTIVE = "descriptive"


CAT_PHYSICOCHEMICAL = "Fisikokimia"
CAT_ABSORPTION = "Absorpsi"
CAT_DISTRIBUTION = "Distribusi"
CAT_METABOLISM = "Metabolisme"
CAT_EXCRETION = "Ekskresi"
CAT_TOXICITY = "Toksisitas"

CATEGORIES = [
    CAT_PHYSICOCHEMICAL, CAT_ABSORPTION, CAT_DISTRIBUTION,
    CAT_METABOLISM, CAT_EXCRETION, CAT_TOXICITY,
]

EXCLUDED_COLUMNS = frozenset({"raw_smiles", "smiles", "molstr", "ligand", "ligand_name", "ligand_code", "group"})

FLAG_SCORE = {Flag.GREEN: 1.0, Flag.YELLOW: 0.5, Flag.RED: 0.0}

_ALERT_EMPTY = "['-']"
_COLUMN_ALIASES = {"logVDss": "VDss"}


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text == _ALERT_EMPTY or text.lower() == "nan":
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ClassificationResult:
    flag: Flag
    label: str
    value: Any = None


@dataclass(frozen=True)
class AdmetRule:
    column: str
    category: str
    label: str
    unit: str = ""
    rule_type: RuleType = RuleType.DESCRIPTIVE
    lo: Optional[float] = None
    hi: Optional[float] = None
    breakpoints: Optional[tuple] = None
    ascending_bad: bool = True
    inverted: bool = False
    citation: str = ""
    note: str = ""
    descriptive_fn: Optional[Callable[[float], str]] = None

    @property
    def scored(self) -> bool:
        return self.rule_type != RuleType.DESCRIPTIVE

    def classify(self, raw_value: Any) -> ClassificationResult:
        rt = self.rule_type

        if rt == RuleType.ALERT_COUNT:
            return self._classify_alert(raw_value)
        if rt == RuleType.DESCRIPTIVE:
            return self._classify_descriptive(raw_value)
        if rt == RuleType.BINARY:
            return self._classify_binary(raw_value)

        v = _coerce_float(raw_value)
        if v is None:
            return ClassificationResult(Flag.NA, "N/A", raw_value)

        if rt == RuleType.RANGE:
            ok = self.lo <= v <= self.hi
            return ClassificationResult(Flag.GREEN if ok else Flag.RED, "Optimal" if ok else "Di luar rentang", v)
        if rt == RuleType.THRESHOLD_GTE:
            ok = v >= self.lo
            return ClassificationResult(Flag.GREEN if ok else Flag.RED, "Baik" if ok else "Buruk", v)
        if rt == RuleType.THRESHOLD_LTE:
            ok = v <= self.hi
            return ClassificationResult(Flag.GREEN if ok else Flag.RED, "Baik" if ok else "Buruk", v)
        if rt == RuleType.TIERED:
            return self._classify_tiered(v, reverse=False)
        if rt == RuleType.TIERED_REVERSED:
            return self._classify_tiered(v, reverse=True)
        if rt == RuleType.TIERED_RANGE:
            return self._classify_tiered_range(v)
        return ClassificationResult(Flag.NA, "N/A", v)

    def _classify_alert(self, raw_value: Any) -> ClassificationResult:
        if raw_value is None:
            return ClassificationResult(Flag.NA, "N/A", raw_value)
        text = str(raw_value).strip()
        if text == "" or text == _ALERT_EMPTY or text.lower() == "nan":
            return ClassificationResult(Flag.GREEN, "Tanpa peringatan", raw_value)
        v = _coerce_float(raw_value)
        if v is not None:
            if v == 0:
                return ClassificationResult(Flag.GREEN, "Tanpa peringatan", raw_value)
            return ClassificationResult(Flag.RED, "Ada peringatan", raw_value)
        return ClassificationResult(Flag.RED, "Ada peringatan", raw_value)

    def _classify_descriptive(self, raw_value: Any) -> ClassificationResult:
        if raw_value is None:
            return ClassificationResult(Flag.NA, "N/A", raw_value)
        if isinstance(raw_value, str) and raw_value.strip() in ("", _ALERT_EMPTY):
            return ClassificationResult(Flag.NA, "N/A", raw_value)
        v = _coerce_float(raw_value)
        if v is not None and self.descriptive_fn is not None:
            return ClassificationResult(Flag.INFO, self.descriptive_fn(v), v)
        if v is not None:
            return ClassificationResult(Flag.INFO, f"{v:g}", v)
        return ClassificationResult(Flag.INFO, str(raw_value), raw_value)

    def _classify_binary(self, raw_value: Any) -> ClassificationResult:
        v = _coerce_float(raw_value)
        if v is None:
            return ClassificationResult(Flag.NA, "N/A", raw_value)
        value = int(round(v))
        is_green = (value == 0) if self.inverted else (value == 1)
        return ClassificationResult(Flag.GREEN if is_green else Flag.RED, "Baik" if is_green else "Buruk", v)

    @staticmethod
    def _classify_tiered(v: float, reverse: bool) -> ClassificationResult:
        if v <= 0.3:
            return ClassificationResult(Flag.RED if reverse else Flag.GREEN, "Buruk" if reverse else "Sangat baik", v)
        if v <= 0.7:
            return ClassificationResult(Flag.YELLOW, "Sedang", v)
        return ClassificationResult(Flag.GREEN if reverse else Flag.RED, "Sangat baik" if reverse else "Buruk", v)

    def _classify_tiered_range(self, v: float) -> ClassificationResult:
        low, high = self.breakpoints
        if self.ascending_bad:
            if v <= low:
                return ClassificationResult(Flag.GREEN, "Sangat baik", v)
            if v <= high:
                return ClassificationResult(Flag.YELLOW, "Sedang", v)
            return ClassificationResult(Flag.RED, "Buruk", v)
        if v > high:
            return ClassificationResult(Flag.GREEN, "Sangat baik", v)
        if v >= low:
            return ClassificationResult(Flag.YELLOW, "Sedang", v)
        return ClassificationResult(Flag.RED, "Buruk", v)


def _melting_label(v: float) -> str:
    return "Cair (<25 C)" if v < 25 else "Padat (>=25 C)"


def _boiling_label(v: float) -> str:
    return "Gas (<25 C)" if v < 25 else "Cair/padat pada suhu ruang (>=25 C)"


_TIERED_NOTE = "Tidak ada skala keputusan khusus di dokumentasi, dipakai pita bertingkat 0,3/0,7."
_SOFT_RULE = "Drug-Like Soft rule"


def _tiered_group(category: str, items: List[tuple], note: str = "") -> List[AdmetRule]:
    return [AdmetRule(col, category, label, rule_type=RuleType.TIERED, note=note) for col, label in items]


_RULES_LIST: List[AdmetRule] = [
    AdmetRule("MW", CAT_PHYSICOCHEMICAL, "Molecular Weight", "Da", RuleType.RANGE, lo=100, hi=600, citation=_SOFT_RULE),
    AdmetRule("Vol", CAT_PHYSICOCHEMICAL, "Volume", "A^3", citation="Van der Waals volume"),
    AdmetRule("Dense", CAT_PHYSICOCHEMICAL, "Density", citation="MW / Volume"),
    AdmetRule("nHA", CAT_PHYSICOCHEMICAL, "H-Bond Acceptors", rule_type=RuleType.RANGE, lo=0, hi=12, citation=_SOFT_RULE),
    AdmetRule("nHD", CAT_PHYSICOCHEMICAL, "H-Bond Donors", rule_type=RuleType.RANGE, lo=0, hi=7, citation=_SOFT_RULE),
    AdmetRule("TPSA", CAT_PHYSICOCHEMICAL, "TPSA", "A^2", RuleType.RANGE, lo=0, hi=140, citation="Veber et al. 2002"),
    AdmetRule("nRot", CAT_PHYSICOCHEMICAL, "Rotatable Bonds", rule_type=RuleType.RANGE, lo=0, hi=11, citation=_SOFT_RULE),
    AdmetRule("nRing", CAT_PHYSICOCHEMICAL, "Ring Count", rule_type=RuleType.RANGE, lo=0, hi=6, citation=_SOFT_RULE),
    AdmetRule("MaxRing", CAT_PHYSICOCHEMICAL, "Max Ring Size", "atoms", RuleType.RANGE, lo=0, hi=18, citation=_SOFT_RULE),
    AdmetRule("nHet", CAT_PHYSICOCHEMICAL, "Heteroatom Count", rule_type=RuleType.RANGE, lo=1, hi=15, citation=_SOFT_RULE),
    AdmetRule("fChar", CAT_PHYSICOCHEMICAL, "Formal Charge", rule_type=RuleType.RANGE, lo=-4, hi=4, citation=_SOFT_RULE),
    AdmetRule("nRig", CAT_PHYSICOCHEMICAL, "Rigid Bonds", rule_type=RuleType.RANGE, lo=0, hi=30, citation=_SOFT_RULE),
    AdmetRule("Flex", CAT_PHYSICOCHEMICAL, "Flexibility", citation="nRot / nRig"),
    AdmetRule("nStereo", CAT_PHYSICOCHEMICAL, "Stereo Centers", rule_type=RuleType.THRESHOLD_LTE, hi=2,
              citation="Lead-Like Soft rule"),
    AdmetRule("logS", CAT_PHYSICOCHEMICAL, "logS", "log mol/L", RuleType.RANGE, lo=-4, hi=0.5,
              citation="Rentang ADMETLab3"),
    AdmetRule("logP", CAT_PHYSICOCHEMICAL, "logP", "log mol/L", RuleType.RANGE, lo=0, hi=3,
              citation="Rentang ADMETLab3"),
    AdmetRule("logD", CAT_PHYSICOCHEMICAL, "logD 7.4", "log mol/L", RuleType.RANGE, lo=1, hi=3,
              citation="Rentang ADMETLab3"),
    AdmetRule("mp", CAT_PHYSICOCHEMICAL, "Melting Point", "C", descriptive_fn=_melting_label),
    AdmetRule("bp", CAT_PHYSICOCHEMICAL, "Boiling Point", "C", descriptive_fn=_boiling_label),
    AdmetRule("pka_acidic", CAT_PHYSICOCHEMICAL, "pKa (acidic)", citation="Makin kecil, asam makin kuat"),
    AdmetRule("pka_basic", CAT_PHYSICOCHEMICAL, "pKa (basic)", citation="Makin besar, basa makin kuat"),
    AdmetRule("QED", CAT_PHYSICOCHEMICAL, "QED", rule_type=RuleType.THRESHOLD_GTE, lo=0.67 + 1e-9,
              citation="Bickerton et al. 2012"),
    AdmetRule("Synth", CAT_PHYSICOCHEMICAL, "SAscore", "1-10", RuleType.THRESHOLD_LTE, hi=6 - 1e-9,
              citation="Ertl & Schuffenhauer 2009"),
    AdmetRule("gasa", CAT_PHYSICOCHEMICAL, "GASA", "0/1", RuleType.BINARY, inverted=True,
              citation="Yu et al. 2022 (0 mudah, 1 sulit)"),
    AdmetRule("Fsp3", CAT_PHYSICOCHEMICAL, "Fsp3", rule_type=RuleType.THRESHOLD_GTE, lo=0.42,
              citation="Lovering et al. 2009"),
    AdmetRule("MCE-18", CAT_PHYSICOCHEMICAL, "MCE-18", rule_type=RuleType.THRESHOLD_GTE, lo=45,
              citation="Ivanenkov et al. 2019"),
    AdmetRule("Natural Product-likeness", CAT_PHYSICOCHEMICAL, "Natural Product-likeness", "-5 sampai 5",
              citation="Ertl et al. 2008"),
    AdmetRule("Alarm_NMR", CAT_PHYSICOCHEMICAL, "ALARM NMR Alerts", rule_type=RuleType.ALERT_COUNT,
              citation="Huth et al. 2005"),
    AdmetRule("BMS", CAT_PHYSICOCHEMICAL, "BMS Alerts", rule_type=RuleType.ALERT_COUNT,
              citation="Pearce et al. 2006"),
    AdmetRule("Chelating", CAT_PHYSICOCHEMICAL, "Chelator Alerts", rule_type=RuleType.ALERT_COUNT,
              citation="Agrawal et al. 2010"),
    AdmetRule("PAINS", CAT_PHYSICOCHEMICAL, "PAINS Alerts", rule_type=RuleType.ALERT_COUNT,
              citation="Baell & Holloway 2010"),
    AdmetRule("Lipinski", CAT_PHYSICOCHEMICAL, "Lipinski Rule", "pelanggaran", RuleType.THRESHOLD_LTE, hi=1,
              citation="Lipinski et al. 1997"),
    AdmetRule("Pfizer", CAT_PHYSICOCHEMICAL, "Pfizer Rule", "pelanggaran", RuleType.THRESHOLD_LTE, hi=1,
              citation="Hughes et al. 2008"),
    AdmetRule("GSK", CAT_PHYSICOCHEMICAL, "GSK Rule", "pelanggaran", RuleType.THRESHOLD_LTE, hi=0,
              citation="Gleeson 2008"),
    AdmetRule("GoldenTriangle", CAT_PHYSICOCHEMICAL, "Golden Triangle", "pelanggaran", RuleType.THRESHOLD_LTE, hi=0,
              citation="Johnson et al. 2009"),
    *_tiered_group(CAT_PHYSICOCHEMICAL, [
        ("Aggregators", "Colloidal Aggregators"),
        ("Fluc", "FLuc Inhibitors"),
        ("Blue_fluorescence", "Blue Fluorescence"),
        ("Green_fluorescence", "Green Fluorescence"),
        ("Reactive", "Reactive Compounds"),
        ("Promiscuous", "Promiscuous Compounds"),
    ]),
    AdmetRule("Other_assay_interference", CAT_PHYSICOCHEMICAL, "Other Assay Interference",
              rule_type=RuleType.TIERED, note=_TIERED_NOTE),

    AdmetRule("caco2", CAT_ABSORPTION, "Caco-2 Permeability", "log cm/s", RuleType.THRESHOLD_GTE, lo=-5.15 + 1e-9),
    AdmetRule("PAMPA", CAT_ABSORPTION, "PAMPA", rule_type=RuleType.TIERED),
    AdmetRule("MDCK", CAT_ABSORPTION, "MDCK Permeability", "log cm/s", RuleType.THRESHOLD_GTE, lo=-5.70,
              note="Ambang linear 2e-6 cm/s dikonversi ke log10 (-5,70) karena kolom CSV berisi log10(Papp)."),
    AdmetRule("pgp_inh", CAT_ABSORPTION, "P-gp Inhibitor", rule_type=RuleType.TIERED),
    AdmetRule("pgp_sub", CAT_ABSORPTION, "P-gp Substrate", rule_type=RuleType.TIERED),
    AdmetRule("hia", CAT_ABSORPTION, "HIA", rule_type=RuleType.TIERED),
    AdmetRule("f20", CAT_ABSORPTION, "F20%", rule_type=RuleType.TIERED),
    AdmetRule("f30", CAT_ABSORPTION, "F30%", rule_type=RuleType.TIERED),
    AdmetRule("f50", CAT_ABSORPTION, "F50%", rule_type=RuleType.TIERED),

    AdmetRule("OATP1B1", CAT_DISTRIBUTION, "OATP1B1 Inhibitor", rule_type=RuleType.TIERED),
    AdmetRule("OATP1B3", CAT_DISTRIBUTION, "OATP1B3 Inhibitor", rule_type=RuleType.TIERED),
    AdmetRule("BCRP", CAT_DISTRIBUTION, "BCRP Inhibitor", rule_type=RuleType.TIERED_REVERSED,
              note="Arah pita kebalikan dari transporter sejenis (OATP1B1/3, BSEP, MRP1)."),
    AdmetRule("BSEP", CAT_DISTRIBUTION, "BSEP Inhibitor", rule_type=RuleType.TIERED),
    AdmetRule("MRP1", CAT_DISTRIBUTION, "MRP1 Inhibitor", rule_type=RuleType.TIERED),
    AdmetRule("PPB", CAT_DISTRIBUTION, "Plasma Protein Binding", "%", RuleType.THRESHOLD_LTE, hi=90),
    AdmetRule("VDss", CAT_DISTRIBUTION, "VDss", "log10(L/kg)", RuleType.RANGE, lo=-1.4, hi=1.3,
              note="Rentang linear 0,04-20 L/kg dikonversi ke log10 karena kolom CSV berisi log10(VDss)."),
    AdmetRule("BBB", CAT_DISTRIBUTION, "BBB Penetration", rule_type=RuleType.TIERED),
    AdmetRule("Fu", CAT_DISTRIBUTION, "Fraction Unbound", "%", RuleType.THRESHOLD_GTE, lo=5,
              note="Nilai CSV sudah dalam skala persen (bukan pecahan 0-1)."),

    *[
        AdmetRule(col, CAT_METABOLISM, label, rule_type=RuleType.TIERED, note=_TIERED_NOTE)
        for col, label in [
            ("CYP1A2-inh", "CYP1A2 Inhibitor"), ("CYP1A2-sub", "CYP1A2 Substrate"),
            ("CYP2C19-inh", "CYP2C19 Inhibitor"), ("CYP2C19-sub", "CYP2C19 Substrate"),
            ("CYP2C9-inh", "CYP2C9 Inhibitor"), ("CYP2C9-sub", "CYP2C9 Substrate"),
            ("CYP2D6-inh", "CYP2D6 Inhibitor"), ("CYP2D6-sub", "CYP2D6 Substrate"),
            ("CYP3A4-inh", "CYP3A4 Inhibitor"), ("CYP3A4-sub", "CYP3A4 Substrate"),
            ("CYP2B6-inh", "CYP2B6 Inhibitor"), ("CYP2B6-sub", "CYP2B6 Substrate"),
            ("CYP2C8-inh", "CYP2C8 Inhibitor"),
        ]
    ],
    AdmetRule("LM-human", CAT_METABOLISM, "HLM Stability", rule_type=RuleType.TIERED_REVERSED,
              note="Keluaran berupa probabilitas ketidakstabilan."),

    AdmetRule("cl-plasma", CAT_EXCRETION, "Plasma Clearance", "mL/min/kg", RuleType.TIERED_RANGE,
              breakpoints=(5, 15), ascending_bad=True),
    AdmetRule("t0.5", CAT_EXCRETION, "Half-life", "jam", RuleType.TIERED_RANGE,
              breakpoints=(1, 8), ascending_bad=False,
              note="Nilai keluaran sering berkumpul dekat batas merah/kuning; tafsirkan dengan hati-hati."),

    *_tiered_group(CAT_TOXICITY, [
        ("Neurotoxicity-DI", "Drug-induced Neurotoxicity"),
        ("Ototoxicity", "Ototoxicity"),
        ("Hematotoxicity", "Hematotoxicity"),
        ("Nephrotoxicity-DI", "Drug-induced Nephrotoxicity"),
        ("Genotoxicity", "Genotoxicity"),
        ("RPMI-8226", "RPMI-8226 Immunotoxicity"),
        ("A549", "A549 Cytotoxicity"),
        ("HEK293", "HEK293 Cytotoxicity"),
        ("hERG-10um", "hERG Blockers (10 uM)"),
        ("hERG", "hERG Blockers"),
        ("H-HT", "Human Hepatotoxicity"),
        ("DILI", "DILI"),
        ("Ames", "Ames Mutagenicity"),
        ("ROA", "Rat Oral Acute Toxicity"),
        ("FDAMDD", "FDAMDD"),
        ("SkinSen", "Skin Sensitization"),
        ("Carcinogenicity", "Carcinogenicity"),
        ("EC", "Eye Corrosion"),
        ("EI", "Eye Irritation"),
        ("Respiratory", "Respiratory Toxicity"),
        ("NR-AhR", "NR-AhR"),
        ("NR-AR", "NR-AR"),
        ("NR-AR-LBD", "NR-AR-LBD"),
        ("NR-Aromatase", "NR-Aromatase"),
        ("NR-ER", "NR-ER"),
        ("NR-ER-LBD", "NR-ER-LBD"),
        ("NR-PPAR-gamma", "NR-PPAR-gamma"),
        ("SR-ARE", "SR-ARE"),
        ("SR-ATAD5", "SR-ATAD5"),
        ("SR-HSE", "SR-HSE"),
        ("SR-MMP", "SR-MMP"),
        ("SR-p53", "SR-p53"),
    ]),
    AdmetRule("BCF", CAT_TOXICITY, "Bioconcentration Factor", "log10(L/kg)"),
    AdmetRule("IGC50", CAT_TOXICITY, "T. pyriformis IGC50", "-log10[(mg/L)/(1000*MW)]"),
    AdmetRule("LC50DM", CAT_TOXICITY, "D. magna LC50", "-log10[(mg/L)/(1000*MW)]"),
    AdmetRule("LC50FM", CAT_TOXICITY, "Fathead Minnow LC50", "-log10[(mg/L)/(1000*MW)]"),
    AdmetRule("LD50_oral", CAT_TOXICITY, "Acute Toxicity Rule", rule_type=RuleType.ALERT_COUNT,
              citation="20 substruktur"),
    AdmetRule("NonBiodegradable", CAT_TOXICITY, "NonBiodegradable Rule", rule_type=RuleType.ALERT_COUNT,
              citation="19 substruktur"),
    AdmetRule("NonGenotoxic_Carcinogenicity", CAT_TOXICITY, "NonGenotoxic Carcinogenicity Rule",
              rule_type=RuleType.ALERT_COUNT, citation="23 substruktur"),
    AdmetRule("SureChEMBL", CAT_TOXICITY, "SureChEMBL Rule", rule_type=RuleType.ALERT_COUNT,
              citation="164 substruktur"),
    AdmetRule("Skin_Sensitization", CAT_TOXICITY, "Skin Sensitization Rule", rule_type=RuleType.ALERT_COUNT,
              citation="155 substruktur"),
    AdmetRule("Acute_Aquatic_Toxicity", CAT_TOXICITY, "Aquatic Toxicity Rule", rule_type=RuleType.ALERT_COUNT,
              citation="99 substruktur"),
    AdmetRule("Genotoxic_Carcinogenicity_Mutagenicity", CAT_TOXICITY, "Genotoxic Carcinogenicity Rule",
              rule_type=RuleType.ALERT_COUNT, citation="117 substruktur"),
    AdmetRule("FAF-Drugs4 Rule", CAT_TOXICITY, "FAF-Drugs4 Rule", rule_type=RuleType.ALERT_COUNT),
]

RULES: Dict[str, AdmetRule] = {rule.column: rule for rule in _RULES_LIST}


def get_rule(column_name: str) -> Optional[AdmetRule]:
    return RULES.get(_COLUMN_ALIASES.get(column_name, column_name))


def classify_admet_value(column_name: str, value: Any) -> ClassificationResult:
    """Klasifikasikan satu nilai sel ADMET; kolom tak dikenal menghasilkan ``Flag.NA``."""
    rule = get_rule(column_name)
    if rule is None:
        return ClassificationResult(Flag.NA, "N/A", value)
    return rule.classify(value)


def categories() -> List[str]:
    return list(CATEGORIES)


def rules_by_category(category: str) -> List[AdmetRule]:
    return [r for r in _RULES_LIST if r.category == category]


def columns_for_category(category: str) -> List[str]:
    return [r.column for r in rules_by_category(category)]


def category_of(column_name: str) -> Optional[str]:
    rule = get_rule(column_name)
    return rule.category if rule else None


def category_scores(admet_row: Dict[str, Any], exclude: tuple = (CAT_PHYSICOCHEMICAL,)) -> Dict[str, float]:
    """Skor rata-rata per kategori (hijau 1, kuning 0,5, merah 0) dari satu baris ADMET.

    Parameter deskriptif dan nilai N/A tidak dihitung. Kategori tanpa satu
    pun parameter terskor pada baris itu dilewati.
    """
    scores: Dict[str, float] = {}
    for category in CATEGORIES:
        if category in exclude:
            continue
        values = []
        for rule in rules_by_category(category):
            if not rule.scored or rule.column not in admet_row:
                continue
            flag = rule.classify(admet_row[rule.column]).flag
            if flag in FLAG_SCORE:
                values.append(FLAG_SCORE[flag])
        if values:
            scores[category] = sum(values) / len(values)
    return scores


def _round_bound(x: float, eps: float = 1e-6) -> tuple:
    rounded = round(x, 6)
    if x != rounded and abs(x - rounded) < eps:
        return rounded, True
    return rounded, False


def threshold_text(rule: AdmetRule) -> str:
    """Deskripsi ambang batas satu aturan, untuk sheet legenda Excel."""
    rt = rule.rule_type
    if rt == RuleType.RANGE:
        return f"{rule.lo:g} sampai {rule.hi:g} hijau, di luar rentang merah"
    if rt == RuleType.THRESHOLD_GTE:
        lo, strict = _round_bound(rule.lo)
        return f"{'>' if strict else '>='} {lo:g} hijau, selain itu merah"
    if rt == RuleType.THRESHOLD_LTE:
        hi, strict = _round_bound(rule.hi)
        return f"{'<' if strict else '<='} {hi:g} hijau, selain itu merah"
    if rt == RuleType.TIERED:
        return "0-0,3 hijau / 0,3-0,7 kuning / 0,7-1,0 merah"
    if rt == RuleType.TIERED_REVERSED:
        return "0-0,3 merah / 0,3-0,7 kuning / 0,7-1,0 hijau"
    if rt == RuleType.TIERED_RANGE:
        low, high = rule.breakpoints
        if rule.ascending_bad:
            return f"<= {low:g} hijau / {low:g}-{high:g} kuning / > {high:g} merah"
        return f"> {high:g} hijau / {low:g}-{high:g} kuning / < {low:g} merah"
    if rt == RuleType.ALERT_COUNT:
        return "tanpa peringatan hijau, ada peringatan merah"
    if rt == RuleType.BINARY:
        return "0 hijau, 1 merah" if rule.inverted else "1 hijau, 0 merah"
    return "informasi saja (tanpa ambang)"
