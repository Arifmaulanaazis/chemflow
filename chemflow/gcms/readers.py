"""
Pembaca data GC-MS lintas format.

Format yang dikenali:
  * Ekspor ASCII/Excel GCMSsolution (Shimadzu) yang berbentuk bagian ``[Header]``,
    ``[MS Chromatogram]``, ``[MS Peak Table]``, dan seterusnya.
  * Tabel Excel/CSV/TSV/TXT apa pun: kromatogram (waktu dan intensitas), banyak
    kromatogram berdampingan (satu kolom per sampel), tabel puncak (RT, area,
    tinggi, nama) dengan judul kolom bahasa Inggris atau Indonesia, serta matriks
    fitur sampel x senyawa hasil perangkat lunak lain.
  * ANDI-MS netCDF (``.cdf``, ``.nc`` klasik), mzML, dan mzXML.

Waktu retensi selalu dinormalkan ke menit. Satuan dideteksi dari selang antar titik
data dan lama analisis, karena ekspor sering berisi RT dalam detik atau dalam menit
yang terkali 1000 (pemisah desimal salah dibaca lokal komputer). Satuan bisa dipaksa
lewat ``rt_unit``.
"""

from __future__ import annotations

import base64
import csv
import glob
import logging
import math
import re
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from chemflow.gcms.models import Chromatogram, FeatureTable, Peak

EXCEL_EXTENSIONS = (".xls", ".xlsx", ".xlsm")
TEXT_EXTENSIONS = (".csv", ".tsv", ".txt", ".dat")
NETCDF_EXTENSIONS = (".cdf", ".nc")
MZ_EXTENSIONS = (".mzml", ".mzxml")
SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS + TEXT_EXTENSIONS + NETCDF_EXTENSIONS + MZ_EXTENSIONS

RT_UNITS = ("auto", "min", "sec", "msec", "min_x1000")
_UNIT_FACTORS = {"min": 1.0, "sec": 1.0 / 60.0, "msec": 1.0 / 60000.0, "min_x1000": 1.0 / 1000.0}
_CANDIDATE_FACTORS = (1.0, 1.0 / 60.0, 1.0 / 1000.0, 1.0 / 60000.0)
_MIN_STEP, _MAX_STEP = 1e-4, 0.5        # menit; selang antar titik yang masuk akal untuk GC-MS
_MIN_RUN, _MAX_RUN = 0.5, 400.0         # menit; lama analisis yang masuk akal
_DENSE_POINTS = 50                      # jumlah titik minimal agar RT dianggap kromatogram, bukan daftar puncak


class GcmsFormatError(ValueError):
    """Berkas tidak bisa dibaca sebagai data GC-MS yang dikenali."""


@dataclass
class GcmsDataset:
    """Hasil pembacaan: kromatogram per sampel atau satu tabel fitur, plus label folder sebagai calon kelas."""
    chromatograms: List[Chromatogram] = field(default_factory=list)
    table: Optional[FeatureTable] = None
    folder_labels: Dict[str, str] = field(default_factory=dict)
    skipped: List[Tuple[Path, str]] = field(default_factory=list)


# ---------------------------------------------------------------- satuan RT

def normalize_rt(rt: Sequence[float], unit: str = "auto", hint: Optional[str] = None,
                 event_msec: Optional[float] = None, prefer: Optional[float] = None) -> Tuple[np.ndarray, float]:
    """RT dalam menit beserta faktor pengali yang dipakai.

    Args:
        rt: nilai RT mentah.
        unit: ``auto`` atau salah satu ``RT_UNITS``.
        hint: satuan yang tertulis di judul kolom (``min``, ``sec``, ``msec``), dipakai sebagai kandidat pertama.
        event_msec: selang pemindaian dalam milidetik bila tercatat di berkas; penentu paling andal.
        prefer: faktor yang sudah dipakai bagian lain berkas yang sama.
    """
    values = np.asarray(rt, dtype=float)
    if unit != "auto":
        if unit not in _UNIT_FACTORS:
            raise ValueError(f"Satuan RT harus salah satu dari {RT_UNITS}, dapat: {unit!r}")
        return values * _UNIT_FACTORS[unit], _UNIT_FACTORS[unit]
    if values.size == 0:
        return values, 1.0

    candidates: List[float] = []
    for factor in (prefer, _UNIT_FACTORS.get(hint or ""), *_CANDIDATE_FACTORS):
        if factor is not None and factor not in candidates:
            candidates.append(factor)
    step = float(np.median(np.diff(np.sort(values)))) if values.size > 2 else 0.0

    if event_msec and step > 0:
        expected = event_msec / 60000.0
        best = min(candidates, key=lambda f: abs(math.log(step * f / expected)))
        if abs(math.log(step * best / expected)) < math.log(2.0):
            return values * best, best
    for factor in candidates:
        if _plausible(values * factor, step * factor):
            return values * factor, factor
    return values, 1.0


def _plausible(rt: np.ndarray, step: float) -> bool:
    high = float(np.nanmax(rt))
    if rt.size >= _DENSE_POINTS:
        return _MIN_STEP <= step <= _MAX_STEP and _MIN_RUN <= high - float(np.nanmin(rt)) <= _MAX_RUN
    return 0.2 <= high <= _MAX_RUN


def _unit_hint(text: str) -> Optional[str]:
    lowered = text.lower()
    if re.search(r"\bmsec\b|\bms\b|millisec", lowered):
        return "msec"
    if re.search(r"\(s\)|\bsec\b|second|detik", lowered):
        return "sec"
    if re.search(r"\bmin\b|minute|menit", lowered):
        return "min"
    return None


# ---------------------------------------------------------------- baris mentah

def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float, np.number)):
        number = float(value)
        return None if math.isnan(number) else number
    text = str(value).strip().replace("\u00a0", "").rstrip("%").strip()
    if not text or text.lower() in {"nan", "n/a", "na", "none", "-", "--"}:
        return None
    if re.fullmatch(r"[-+]?\d+,\d+", text):
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _cell(row: Sequence[Any], index: int) -> Any:
    return row[index] if 0 <= index < len(row) else None


def _sniff_delimiter(lines: Sequence[str]) -> Optional[str]:
    """Pemisah kolom: tab atau titik koma bila muncul di sebagian besar baris, lalu tegak, lalu koma; ``None`` = spasi.

    Koma diperiksa terakhir karena juga dipakai sebagai pemisah desimal pada berkas bertitik koma.
    """
    sample = [line for line in lines if line.strip()][:200]
    if not sample:
        return None
    for delimiter, minimum in (("	", 0.3), (";", 0.3), ("|", 0.5), (",", 0.0)):
        if sum(delimiter in line for line in sample) / len(sample) > minimum:
            return delimiter
    return None


def _text_rows(path: Path) -> List[List[Any]]:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("latin-1")
    lines = text.splitlines()
    delimiter = _sniff_delimiter(lines)
    if delimiter is None:
        return [line.split() for line in lines]
    return [next(csv.reader([line], delimiter=delimiter), []) if line.strip() else [] for line in lines]


def _excel_sheets(path: Path) -> Dict[str, List[List[Any]]]:
    try:
        frames = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    except ImportError as exc:
        raise GcmsFormatError(f"Membaca {path.suffix} butuh paket tambahan: pip install xlrd openpyxl ({exc})") from exc
    except Exception as exc:
        raise GcmsFormatError(f"Excel tidak bisa dibuka: {exc}") from exc
    return {str(name): frame.astype(object).where(pd.notna(frame), None).values.tolist() for name, frame in frames.items()}


# ---------------------------------------------------------------- tabel dalam baris

def _sections(rows: List[List[Any]]) -> List[Tuple[str, List[List[Any]]]]:
    """Pecah baris menjadi bagian berjudul ``[Nama]``; tanpa judul semuanya satu bagian."""
    result: List[Tuple[str, List[List[Any]]]] = []
    name, current = "", []
    for row in rows:
        first = _text(_cell(row, 0))
        if re.fullmatch(r"\[.+\]", first) and all(_text(c) == "" for c in row[1:]):
            result.append((name, current))
            name, current = first[1:-1].strip(), []
        else:
            current.append(row)
    result.append((name, current))
    return [(n, r) for n, r in result if any(any(_text(c) for c in row) for row in r)]


def _classify(header: Sequence[str]) -> Dict[str, int]:
    """Peran tiap kolom (rt, intensity, area, height, name, ...) dari judulnya."""
    roles: Dict[str, int] = {}
    rank = {"intensity_abs": 0, "intensity": 1, "relative": 2}
    for index, raw in enumerate(header):
        h = raw.strip().lower()
        if not h:
            continue
        if "rt" not in roles and re.match(r"^(ret\.?\s*time|r\.?\s*time|rt|retention\s*time|waktu(\s*retensi)?|time|scan\s*time)\b", h) \
                and not re.search(r"proc|from|start|end|to$", h):
            roles["rt"] = index
        elif re.match(r"^(area\s*%|%\s*area|area\s*pct|rel\w*\.?\s*area)", h):
            roles.setdefault("area_pct", index)
        elif h.startswith("area") or h.startswith("luas"):
            roles.setdefault("area", index)
        elif re.match(r"^(height\s*%|%\s*height)", h):
            roles.setdefault("height_pct", index)
        elif h.startswith("height") or h.startswith("tinggi"):
            roles.setdefault("height", index)
        elif re.search(r"abs", h) and re.search(r"intens|abund|signal|counts", h):
            roles.setdefault("intensity_abs", index)
        elif re.match(r"^(relative|rel\.?)\s*(intens|abund)", h):
            roles.setdefault("relative", index)
        elif re.search(r"intens|abund|signal|response|counts|\btic\b|sinyal|respon", h):
            roles.setdefault("intensity", index)
        elif re.match(r"^(name|compound|component|identity|library|peak\s*name|hit\s*name|nama|senyawa)", h):
            roles.setdefault("name", index)
        elif re.match(r"^cas", h):
            roles.setdefault("cas", index)
        elif re.match(r"^(si|sim|similarity|match|quality|qual)\b", h):
            roles.setdefault("similarity", index)
        elif re.match(r"^(proc\.?\s*from|start|i\.?\s*time|begin|rt\s*start)", h):
            roles.setdefault("start", index)
        elif re.match(r"^(proc\.?\s*to|end|f\.?\s*time|rt\s*end)", h):
            roles.setdefault("end", index)
    signal = sorted((rank[k], roles[k]) for k in rank if k in roles)
    if signal:
        roles["signal"] = signal[0][1]
    return roles


def _numeric_run(rows: Sequence[List[Any]], first_numeric: bool) -> List[List[Any]]:
    data: List[List[Any]] = []
    for row in rows:
        cells = [c for c in row if _text(c) != ""]
        if not cells:
            break
        if first_numeric and _to_float(_cell(row, 0)) is None:
            break
        if not first_numeric and not any(_to_float(c) is not None for c in cells):
            break
        data.append(row)
    return data


def _find_table(rows: List[List[Any]]) -> Optional[Tuple[Dict[str, Any], List[str], List[List[Any]]]]:
    """(meta, judul kolom, baris data) tabel pertama pada sebuah bagian; ``meta`` dari baris kunci dan nilai di atasnya."""
    meta: Dict[str, Any] = {}
    for strict in (True, False):
        meta = {}
        for index, row in enumerate(rows):
            cells = [c for c in row if _text(c) != ""]
            if not cells:
                continue
            following = rows[index + 1] if index + 1 < len(rows) else []
            if _to_float(_cell(row, 0)) is not None:
                if strict and len(cells) >= 2:
                    return meta, [], _numeric_run(rows[index:], True)
                continue
            all_text = all(_to_float(c) is None for c in cells)
            if all_text and len(cells) >= 2:
                header = [_text(c) for c in row]
                if strict and _to_float(_cell(following, 0)) is not None:
                    return meta, header, _numeric_run(rows[index + 1:], True)
                if not strict and "rt" in _classify(header) and any(_to_float(c) is not None for c in following):
                    return meta, header, _numeric_run(rows[index + 1:], False)
            if len(cells) >= 2 and _text(row[0]):
                meta[_text(row[0]).lower()] = _cell(row, 1)
    return None


def _collect_meta(rows: List[List[Any]]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    for row in rows:
        key, value = _text(_cell(row, 0)), _cell(row, 1)
        if key and not key.startswith("[") and _text(value) != "" and _to_float(key) is None:
            meta.setdefault(key.lower(), value)
    return meta


def _column(data: List[List[Any]], index: int) -> np.ndarray:
    return np.array([(_to_float(_cell(row, index)) if _to_float(_cell(row, index)) is not None else np.nan) for row in data])


def _clean_signal(rt: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    keep = np.isfinite(rt)
    rt, y = rt[keep], np.nan_to_num(y[keep], nan=0.0)
    order = np.argsort(rt, kind="stable")
    rt, y = rt[order], y[order]
    unique = np.concatenate(([True], np.diff(rt) > 0))
    return rt[unique], y[unique]


@dataclass
class _Block:
    signals: List[Tuple[str, np.ndarray, np.ndarray]] = field(default_factory=list)
    multi: bool = False
    peaks: List[Peak] = field(default_factory=list)
    factor: float = 1.0
    meta: Dict[str, Any] = field(default_factory=dict)


def _parse_block(rows: List[List[Any]], unit: str, prefer: Optional[float]) -> Optional[_Block]:
    found = _find_table(rows)
    if found is None:
        return None
    meta, header, data = found
    if len(data) < 2 and not header:
        return None
    if header:
        roles = _classify(header)
    else:
        width = max(len(r) for r in data)
        roles = {"rt": 0, "signal": 1} if width >= 2 else {}
    if "rt" not in roles or not data:
        return None

    hint = _unit_hint(header[roles["rt"]]) if header else None
    event_msec = _to_float(next((v for k, v in meta.items() if k.startswith("event time")), None))
    rt_raw = _column(data, roles["rt"])
    rt, factor = normalize_rt(rt_raw[np.isfinite(rt_raw)], unit, hint, event_msec, prefer)
    block = _Block(factor=factor, meta=meta)
    label = str(meta.get("m/z", "")).strip() or (header[roles["signal"]] if header and "signal" in roles else "")

    if "signal" in roles:
        rt_all = _column(data, roles["rt"]) * factor
        block.signals.append((label, *_clean_signal(rt_all, _column(data, roles["signal"]))))
    elif "area" in roles or "height" in roles:
        for row in data:
            value = _to_float(_cell(row, roles["rt"]))
            if value is None:
                continue
            def pick(role: str, default: float = float("nan")) -> float:
                got = _to_float(_cell(row, roles[role])) if role in roles else None
                return default if got is None else got
            block.peaks.append(Peak(
                rt=value * factor, height=pick("height", 0.0), area=pick("area", 0.0), area_pct=pick("area_pct"),
                start=pick("start") * factor, end=pick("end") * factor, similarity=pick("similarity"),
                name=_text(_cell(row, roles["name"])) if "name" in roles else "",
                cas=_text(_cell(row, roles["cas"])) if "cas" in roles else "",
            ))
    else:
        others = [i for i in range(len(header)) if i != roles["rt"] and header[i].strip()]
        rt_all = _column(data, roles["rt"]) * factor
        for i in others:
            values = _column(data, i)
            if np.isfinite(values).sum() >= max(2, len(data) // 2):
                block.signals.append((header[i].strip(), *_clean_signal(rt_all, values)))
        block.multi = len(block.signals) > 0
    return block


def _feature_table(rows: List[List[Any]], name: str) -> Optional[FeatureTable]:
    """Matriks sampel x fitur: kolom pertama teks, sisanya angka. Bila judul pojok kiri menyebut fitur, ditransposisi."""
    rows = [r for r in rows if any(_text(c) for c in r)]
    if len(rows) < 3:
        return None
    header, body = rows[0], rows[1:]
    first_column = [_text(_cell(r, 0)) for r in body]
    if not all(first_column) or all(_to_float(v) is not None for v in first_column):
        return None
    width = max(len(r) for r in rows)
    numeric = [i for i in range(1, width)
               if sum(_to_float(_cell(r, i)) is not None for r in body) >= max(2, int(0.6 * len(body)))]
    if len(numeric) < 2:
        return None
    values = np.nan_to_num(np.array([[(_to_float(_cell(r, i)) or 0.0) for i in numeric] for r in body]))
    features = [_text(_cell(header, i)) or f"F{i}" for i in numeric]
    samples = first_column
    if re.match(r"^(feature|compound|component|peak|rt|retention|metabolite|m/z|senyawa|puncak)", _text(_cell(header, 0)).lower()):
        samples, features, values = features, samples, values.T
    return FeatureTable(samples=list(samples), features=list(features), values=values, source=name)


# ---------------------------------------------------------------- dari baris ke sampel

def _parse_rows(rows: List[List[Any]], name: str, unit: str) -> Tuple[List[Chromatogram], Optional[FeatureTable]]:
    file_meta = _collect_meta(rows)
    blocks: List[_Block] = []
    prefer: Optional[float] = None
    for _, section_rows in _sections(rows):
        block = _parse_block(section_rows, unit, prefer)
        if block is not None and (block.signals or block.peaks):
            blocks.append(block)
            if block.signals and prefer is None:
                prefer = block.factor

    multi = next((b for b in blocks if b.multi), None)
    if multi is not None:
        return [Chromatogram(label, rt, y, source=name, meta=dict(file_meta)) for label, rt, y in multi.signals], None

    peaks = [p for b in blocks for p in b.peaks]
    signals = [s for b in blocks for s in b.signals]
    if signals:
        label, rt, y = next((s for s in signals if "tic" in s[0].lower()), signals[0])
        meta = dict(file_meta)
        meta["signal_label"] = label
        return [Chromatogram(name, rt, y, peaks=peaks, source=name, meta=meta)], None
    if peaks:
        return [Chromatogram(name, peaks=peaks, source=name, meta=dict(file_meta))], None
    table = _feature_table([r for _, section in _sections(rows) for r in section], name)
    return [], table


# ---------------------------------------------------------------- format biner dan XML

def _read_cdf(path: Path) -> Chromatogram:
    from scipy.io import netcdf_file

    try:
        handle = netcdf_file(str(path), "r", mmap=False)
    except (TypeError, ValueError, OSError) as exc:
        raise GcmsFormatError(
            f"{path.name} bukan netCDF klasik (ANDI-MS). Ekspor ulang sebagai ANDI/CDF klasik atau mzML. ({exc})"
        ) from exc
    with handle as nc:
        variables = nc.variables
        if "scan_acquisition_time" not in variables:
            raise GcmsFormatError(f"{path.name}: variabel scan_acquisition_time tidak ada, bukan CDF ANDI-MS.")
        seconds = np.array(variables["scan_acquisition_time"][:], dtype=float)
        if "total_intensity" in variables:
            tic = np.array(variables["total_intensity"][:], dtype=float)
        else:
            values = np.array(variables["intensity_values"][:], dtype=float)
            starts = np.array(variables["scan_index"][:], dtype=int)
            tic = np.array([chunk.sum() for chunk in np.split(values, starts[1:])])
        meta = {str(k): (v.decode(errors="ignore") if isinstance(v, bytes) else v)
                for k, v in getattr(nc, "_attributes", {}).items()}
    rt, tic = _clean_signal(seconds / 60.0, tic)
    return Chromatogram(path.stem, rt, tic, source=path.name, meta=meta)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _cv_params(element: ET.Element) -> Dict[str, Tuple[str, str]]:
    return {c.get("accession", ""): (c.get("value", ""), c.get("unitName", ""))
            for c in element.iter() if _local(c.tag) == "cvParam"}


_MZML_DTYPES = {"MS:1000523": "<f8", "MS:1000521": "<f4", "MS:1000522": "<i8", "MS:1000519": "<i4"}


def _mzml_array(element: ET.Element) -> Tuple[str, np.ndarray]:
    cv = _cv_params(element)
    binary = next((c for c in element if _local(c.tag) == "binary"), None)
    raw = base64.b64decode((binary.text or "") if binary is not None else "")
    if "MS:1000574" in cv:
        raw = zlib.decompress(raw)
    dtype = next((d for k, d in _MZML_DTYPES.items() if k in cv), "<f8")
    kind = "mz" if "MS:1000514" in cv else "intensity" if "MS:1000515" in cv else "time" if "MS:1000595" in cv else ""
    return kind, np.frombuffer(raw, dtype=dtype).astype(float)


def _read_mzml(path: Path) -> Chromatogram:
    times: List[float] = []
    totals: List[float] = []
    chromatogram: Optional[Tuple[np.ndarray, np.ndarray]] = None
    for _, element in ET.iterparse(str(path), events=("end",)):
        tag = _local(element.tag)
        if tag == "chromatogram" and chromatogram is None and "TIC" in (element.get("id") or "").upper():
            arrays = dict(_mzml_array(a) for a in element.iter() if _local(a.tag) == "binaryDataArray")
            if "time" in arrays and "intensity" in arrays:
                unit = next((u for _, u in _cv_params(element).values() if u), "minute")
                chromatogram = (arrays["time"] * (1.0 if unit.lower().startswith("min") else 1 / 60.0), arrays["intensity"])
        elif tag == "spectrum":
            cv = _cv_params(element)
            if cv.get("MS:1000511", ("1", ""))[0] in ("1", ""):
                start = cv.get("MS:1000016")
                if start is not None and start[0] != "":
                    scale = 1.0 if start[1].lower().startswith("min") or not start[1] else 1 / 60.0
                    total = cv.get("MS:1000285")
                    if total is not None and total[0] != "":
                        value = float(total[0])
                    else:
                        arrays = dict(_mzml_array(a) for a in element.iter() if _local(a.tag) == "binaryDataArray")
                        value = float(arrays.get("intensity", np.empty(0)).sum())
                    times.append(float(start[0]) * scale)
                    totals.append(value)
            element.clear()
    if chromatogram is not None:
        rt, tic = _clean_signal(*chromatogram)
    elif times:
        rt, tic = _clean_signal(np.array(times), np.array(totals))
    else:
        raise GcmsFormatError(f"{path.name}: tidak ada spektrum MS1 atau kromatogram TIC pada mzML.")
    return Chromatogram(path.stem, rt, tic, source=path.name)


def _read_mzxml(path: Path) -> Chromatogram:
    times: List[float] = []
    totals: List[float] = []
    for _, element in ET.iterparse(str(path), events=("end",)):
        if _local(element.tag) != "scan":
            continue
        if element.get("msLevel", "1") == "1" and element.get("retentionTime"):
            match = re.fullmatch(r"PT([\d.eE+-]+)([SM])", element.get("retentionTime", ""))
            if match:
                seconds = float(match.group(1)) * (1.0 if match.group(2) == "S" else 60.0)
                total = element.get("totIonCurrent")
                if total is None:
                    peaks = next((c for c in element if _local(c.tag) == "peaks"), None)
                    total = 0.0 if peaks is None else _mzxml_total(peaks)
                times.append(seconds / 60.0)
                totals.append(float(total))
        element.clear()
    if not times:
        raise GcmsFormatError(f"{path.name}: tidak ada pemindaian MS1 pada mzXML.")
    rt, tic = _clean_signal(np.array(times), np.array(totals))
    return Chromatogram(path.stem, rt, tic, source=path.name)


def _mzxml_total(peaks: ET.Element) -> float:
    raw = base64.b64decode(peaks.text or "")
    if peaks.get("compressionType", "none").lower() == "zlib":
        raw = zlib.decompress(raw)
    values = np.frombuffer(raw, dtype=">f8" if peaks.get("precision", "32") == "64" else ">f4")
    return float(values[1::2].sum())


# ---------------------------------------------------------------- pintu masuk

def read_file(path: "str | Path", rt_unit: str = "auto") -> Tuple[List[Chromatogram], Optional[FeatureTable]]:
    """Baca satu berkas menjadi daftar kromatogram (biasanya satu) atau satu tabel fitur.

    Raises:
        GcmsFormatError: format tidak dikenal atau isi tidak bisa ditafsirkan.
    """
    path = Path(path)
    extension = path.suffix.lower()
    if extension in NETCDF_EXTENSIONS:
        return [_read_cdf(path)], None
    if extension == ".mzml":
        return [_read_mzml(path)], None
    if extension == ".mzxml":
        return [_read_mzxml(path)], None
    if extension in EXCEL_EXTENSIONS:
        sheets = _excel_sheets(path)
    elif extension in TEXT_EXTENSIONS:
        sheets = {"": _text_rows(path)}
    else:
        raise GcmsFormatError(f"Ekstensi {extension or '(kosong)'} tidak didukung. Didukung: {', '.join(SUPPORTED_EXTENSIONS)}")

    chromatograms: List[Chromatogram] = []
    tables: List[FeatureTable] = []
    for sheet, rows in sheets.items():
        label = path.stem if len(sheets) == 1 or not sheet else f"{path.stem}_{sheet}"
        found, table = _parse_rows(rows, label, rt_unit)
        chromatograms.extend(found)
        if table is not None:
            tables.append(table)
    for item in chromatograms:
        item.source = path.name
    if not chromatograms and not tables:
        raise GcmsFormatError(
            f"{path.name}: tidak ada kromatogram, tabel puncak, atau tabel fitur yang bisa dikenali. "
            f"Kromatogram butuh kolom waktu (RT/Ret.Time) dan intensitas; tabel puncak butuh RT dan Area atau Height."
        )
    return chromatograms, (tables[0] if tables else None)


def collect_files(inputs: Iterable["str | Path"], exclude_dirs: Sequence[Path] = ()) -> List[Tuple[Path, Optional[str]]]:
    """Uraikan berkas, folder, dan pola (glob) menjadi (berkas, subfolder-tingkat-pertama atau None).

    Berkas dalam ``exclude_dirs`` (mis. folder keluaran analisis sendiri) dilewati.
    """
    excluded = [Path(d).resolve() for d in exclude_dirs]
    found: List[Tuple[Path, Optional[str]]] = []
    seen = set()

    def add(file: Path, label: Optional[str]) -> None:
        resolved = file.resolve()
        if resolved in seen or file.name.startswith(("~$", ".")):
            return
        if any(resolved == d or d in resolved.parents for d in excluded):
            return
        seen.add(resolved)
        found.append((file, label))

    for item in inputs:
        item = Path(item)
        if any(ch in str(item) for ch in "*?["):
            for match in sorted(glob.glob(str(item), recursive=True)):
                if Path(match).is_file():
                    add(Path(match), None)
        elif item.is_dir():
            for file in sorted(item.rglob("*")):
                if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS:
                    relative = file.relative_to(item)
                    add(file, relative.parts[0] if len(relative.parts) > 1 else None)
        elif item.is_file():
            add(item, None)
        else:
            raise FileNotFoundError(f"Data GC-MS tidak ditemukan: {item}")
    return found


def read_data(inputs: Iterable["str | Path"], rt_unit: str = "auto", exclude_dirs: Sequence[Path] = (),
              logger: Optional[logging.Logger] = None) -> GcmsDataset:
    """Baca semua berkas masukan. Berkas yang gagal dicatat di ``skipped``, bukan menghentikan seluruhnya."""
    log = logger or logging.getLogger(__name__)
    dataset = GcmsDataset()
    files = collect_files(inputs, exclude_dirs)
    if not files:
        raise FileNotFoundError("Tidak ada berkas GC-MS yang didukung pada masukan. "
                                f"Ekstensi didukung: {', '.join(SUPPORTED_EXTENSIONS)}")
    entries: List[Tuple[Chromatogram, Path, Optional[str]]] = []
    for file, label in files:
        try:
            chromatograms, table = read_file(file, rt_unit)
        except GcmsFormatError as exc:
            log.warning(f"Dilewati: {exc}")
            dataset.skipped.append((file, str(exc)))
            continue
        if table is not None and not chromatograms:
            if dataset.table is None:
                dataset.table = table
            else:
                log.warning(f"{file.name}: tabel fitur kedua diabaikan, hanya satu tabel fitur yang dipakai.")
            continue
        entries.extend((item, file, label) for item in chromatograms)

    counts: Dict[str, int] = {}
    for item, _, _ in entries:
        counts[item.name] = counts.get(item.name, 0) + 1
    used: Dict[str, int] = {}
    for item, file, label in entries:
        item.meta["original_name"] = item.name
        if counts[item.name] > 1:
            item.name = f"{item.name} ({label or file.parent.name})"
        used[item.name] = used.get(item.name, 0) + 1
        if used[item.name] > 1:
            item.name = f"{item.name}_{used[item.name]}"
        if label:
            dataset.folder_labels[item.name] = label
        dataset.chromatograms.append(item)
    if dataset.chromatograms and dataset.table is not None:
        log.warning("Kromatogram dan tabel fitur sama-sama ada; tabel fitur diabaikan, kromatogram yang dianalisis.")
        dataset.table = None
    if not dataset.chromatograms and dataset.table is None:
        raise GcmsFormatError("Tidak ada data GC-MS yang bisa dibaca dari masukan.")
    return dataset
