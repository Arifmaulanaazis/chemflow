"""Model data GC-MS: puncak, kromatogram, tabel fitur, dan penurunan metadata sampel dari nama."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

_REPLICATE_TAIL = re.compile(
    r"^(?P<base>.+?)(?:[\s_\-]+(?:rep|ulangan|no\.?|#)?[\s_\-]*|[\s_\-]*(?:rep|ulangan)[\s_\-]*)?\(?\d{1,3}\)?$",
    re.IGNORECASE,
)
ORIGINAL_TOKENS = {"asli", "original", "ori", "authentic", "genuine", "real", "reference", "referensi"}
IMITATION_TOKENS = {"tiruan", "imitation", "fake", "palsu", "counterfeit", "kw", "replica", "clone", "dupe"}
DEFAULT_CLASS = "Sampel"


@dataclass
class Peak:
    """Satu puncak kromatogram. ``area``/``height`` dalam satuan intensitas asli, ``rt`` dalam menit."""
    rt: float
    height: float = 0.0
    area: float = 0.0
    area_pct: float = float("nan")
    start: float = float("nan")
    end: float = float("nan")
    snr: float = float("nan")
    name: str = ""
    cas: str = ""
    similarity: float = float("nan")


@dataclass
class Chromatogram:
    """Satu sampel: TIC (bila ada sinyal) dan/atau tabel puncak dari laporan instrumen."""
    name: str
    rt: np.ndarray = field(default_factory=lambda: np.empty(0))
    intensity: np.ndarray = field(default_factory=lambda: np.empty(0))
    peaks: List[Peak] = field(default_factory=list)
    source: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    series: str = ""
    group: str = ""

    @property
    def has_signal(self) -> bool:
        return self.rt.size > 1

    @property
    def scan_interval(self) -> float:
        """Selang antar titik data dalam menit (median), 0 bila tidak ada sinyal."""
        return float(np.median(np.diff(self.rt))) if self.has_signal else 0.0


@dataclass
class FeatureTable:
    """Matriks sampel x fitur yang sudah terkuantifikasi (mis. hasil MZmine/XCMS atau tabel senyawa)."""
    samples: List[str]
    features: List[str]
    values: np.ndarray
    source: str = ""

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values, dtype=float)


def infer_series(name: str) -> str:
    """Nama seri dari nama sampel dengan penanda ulangan di ujung dibuang ("AQUATIC 2" menjadi "AQUATIC")."""
    match = _REPLICATE_TAIL.match(name.strip())
    base = match.group("base").strip(" _-") if match else ""
    return base if re.search(r"[A-Za-z]", base) else name.strip()


def infer_class(name: str) -> Optional[str]:
    """Kelas dari kata kunci pada nama (asli atau tiruan), ``None`` bila tidak ada petunjuk."""
    tokens = set(re.split(r"[\s_\-\.\(\)]+", name.lower()))
    if tokens & ORIGINAL_TOKENS:
        return "Asli"
    if tokens & IMITATION_TOKENS:
        return "Tiruan"
    return None
