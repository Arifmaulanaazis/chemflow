"""
Orkestrasi analisis GC-MS: baca data, proses sinyal, bentuk fitur, jalankan statistik
dan grafik, lalu tulis satu workbook Excel, folder grafik, dan daftar senyawa untuk docking.

Analisis ini opsional dan berdiri sendiri: tidak butuh docking, dan bisa dijalankan
ulang kapan saja terhadap folder keluaran yang sama (``chemflow gcms --output``).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from chemflow.analytics.hca import HierarchicalClustering
from chemflow.analytics.pca import SCALING_METHODS, ChemometricPCA, PcaResult
from chemflow.analytics.style import normalize_formats
from chemflow.gcms import library as lib
from chemflow.gcms import processing as proc
from chemflow.gcms import stats
from chemflow.gcms.models import DEFAULT_CLASS, Chromatogram, FeatureTable, Peak, infer_class, infer_series
from chemflow.gcms.plots import GcmsPlotter, MAX_ANNOTATED_SAMPLES
from chemflow.gcms.readers import RT_UNITS, GcmsDataset, read_data

FEATURE_MODES = ("peaks", "bins")
LABEL_MODES = ("auto", "class", "series")
GCMS_DIRNAME = "gcms"
CONFIG_FILENAME = "gcms_config.json"
_PATH_FIELDS = ("groups_file", "library", "alkanes")


@dataclass
class GcmsConfig:
    """Parameter analisis GC-MS. Semua opsional kecuali ``data`` dan ``output_dir``."""
    data: Tuple[Path, ...]
    output_dir: Path                                  # folder run; hasil ditulis di <output_dir>/gcms
    groups_file: Optional[Path] = None                # tabel sampel, seri, kelas
    library: Optional[Path] = None                    # pustaka senyawa (nama, RT atau RI, CAS, SMILES)
    alkanes: Optional[Path] = None                    # deret alkana untuk indeks Kovats
    rt_unit: str = "auto"
    rt_range: Optional[Tuple[float, float]] = None    # menit; memotong pelarut awal atau ekor kromatogram
    baseline: bool = True
    smooth_window: float = 0.02                       # menit
    min_snr: float = 5.0
    min_prominence: float = 0.005                     # pecahan puncak terbesar
    align: bool = True
    max_shift: float = 0.3                            # menit
    peak_tolerance: float = 0.05                      # menit, pengelompokan puncak antar sampel
    min_presence: float = 0.0                         # pecahan sampel minimal yang memiliki puncak
    feature_mode: str = "peaks"                       # peaks atau bins
    bin_width: float = 0.05                           # menit
    normalization: str = "total"
    transform: str = "none"
    scaling: str = "pareto"
    label_by: str = "auto"                            # kelompok untuk statistik: auto, class, series
    rt_tolerance: float = 0.05                        # menit, pencocokan pustaka lewat RT
    ri_tolerance: float = 10.0                        # satuan indeks, pencocokan lewat RI
    n_permutations: int = 200
    top_features: int = 30
    make_plots: bool = True
    dpi: int = 300
    figure_formats: Tuple[str, ...] = ("png",)
    seed: int = 0

    def __post_init__(self) -> None:
        self.data = tuple(Path(p) for p in ([self.data] if isinstance(self.data, (str, Path)) else self.data))
        self.output_dir = Path(self.output_dir)
        for name in _PATH_FIELDS:
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, Path(value))
        self.figure_formats = normalize_formats(self.figure_formats)
        checks = ((self.rt_unit, RT_UNITS, "rt_unit"), (self.feature_mode, FEATURE_MODES, "feature_mode"),
                  (self.normalization, proc.NORMALIZATIONS, "normalization"), (self.transform, proc.TRANSFORMS, "transform"),
                  (self.scaling, SCALING_METHODS, "scaling"), (self.label_by, LABEL_MODES, "label_by"))
        for value, allowed, name in checks:
            if value not in allowed:
                raise ValueError(f"{name} harus salah satu dari {allowed}, dapat: {value!r}")
        if not self.data:
            raise ValueError("Data GC-MS kosong: berikan minimal satu berkas atau folder.")
        for name in ("min_snr", "smooth_window", "max_shift", "peak_tolerance", "bin_width"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} tidak boleh negatif, dapat: {getattr(self, name)}")
        if self.bin_width <= 0 or self.peak_tolerance <= 0:
            raise ValueError("bin_width dan peak_tolerance harus lebih dari nol.")
        if not 0.0 <= self.min_presence <= 1.0:
            raise ValueError(f"min_presence harus 0 sampai 1, dapat: {self.min_presence}")
        if self.rt_range is not None:
            self.rt_range = (float(self.rt_range[0]), float(self.rt_range[1]))
            if self.rt_range[1] <= self.rt_range[0]:
                raise ValueError(f"rt_range harus (awal, akhir) dengan akhir lebih besar, dapat: {self.rt_range}")

    @property
    def gcms_dir(self) -> Path:
        return self.output_dir / GCMS_DIRNAME

    @property
    def plots_dir(self) -> Path:
        return self.gcms_dir / "plots"

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, Path):
                value = str(value)
            elif isinstance(value, tuple):
                value = [str(v) if isinstance(v, Path) else v for v in value]
            data[item.name] = value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GcmsConfig":
        known = {item.name for item in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if kwargs.get("rt_range") is not None:
            kwargs["rt_range"] = tuple(kwargs["rt_range"])
        if "figure_formats" in kwargs:
            kwargs["figure_formats"] = tuple(kwargs["figure_formats"])
        return cls(**kwargs)


@dataclass
class SampleMeta:
    name: str
    series: str
    group: str


@dataclass
class GcmsResult:
    """Hasil analisis: tabel utama sebagai DataFrame dan path berkas yang ditulis."""
    samples: pd.DataFrame
    features: pd.DataFrame
    workbook: Optional[Path] = None
    plots: List[Path] = field(default_factory=list)
    ligands_file: Optional[Path] = None
    tables: Dict[str, pd.DataFrame] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def read_groups_table(path: "str | Path") -> pd.DataFrame:
    """Tabel metadata sampel dari CSV/Excel: kolom sampel, seri (opsional), kelas (opsional)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Berkas kelompok sampel tidak ditemukan: {path}")
    frame = pd.read_excel(path, dtype=str) if path.suffix.lower() in (".xls", ".xlsx", ".xlsm") \
        else pd.read_csv(path, sep=None, engine="python", dtype=str)
    lookup = {str(c).strip().lower(): c for c in frame.columns}

    def column(*names: str) -> Optional[str]:
        return next((lookup[n] for n in names if n in lookup), None)

    sample = column("sample", "sampel", "name", "nama", "file", "id") or frame.columns[0]
    series = column("series", "seri", "product", "produk", "type", "tipe", "parfum", "perfume", "brand")
    group = column("class", "kelas", "group", "grup", "kelompok", "label", "category", "kategori")
    if series is None and group is None:
        raise ValueError(f"{path.name} butuh kolom seri (series/seri) dan/atau kelas (class/kelas). Kolom ada: {list(frame.columns)}")
    result = pd.DataFrame({"sample": frame[sample].astype(str).str.strip()})
    result["series"] = frame[series].astype(str).str.strip() if series else ""
    result["group"] = frame[group].astype(str).str.strip() if group else ""
    return result.replace({"nan": "", "None": ""})


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", Path(str(text)).stem.lower() if "." in str(text) else str(text).lower())


def assign_metadata(names: Sequence[str], folder_labels: Dict[str, str], groups: Optional[pd.DataFrame],
                    logger: logging.Logger, originals: Optional[Sequence[str]] = None) -> List[SampleMeta]:
    """Seri dan kelas tiap sampel: tabel kelompok, lalu label folder, lalu kata kunci nama, lalu bawaan.

    Seri bawaan adalah nama sampel tanpa nomor ulangan ("AQUATIC 2" menjadi "AQUATIC"). Label folder hanya
    dipakai sebagai kelas bila ada minimal dua folder berbeda. ``originals`` adalah nama berkas sebelum diberi
    akhiran folder (untuk berkas kembar di folder berbeda) dan dipakai untuk penurunan seri dan kelas.
    """
    originals = list(originals) if originals is not None else list(names)
    table = {}
    if groups is not None:
        table = {_key(row.sample): row for row in groups.itertuples()}
        unmatched = [name for name, base in zip(names, originals) if _key(name) not in table and _key(base) not in table]
        if unmatched:
            logger.warning(f"{len(unmatched)} sampel tidak ada di tabel kelompok, memakai penurunan otomatis: "
                           f"{', '.join(unmatched[:5])}{' ...' if len(unmatched) > 5 else ''}")
    folder_ok = len(set(folder_labels.values())) >= 2
    result: List[SampleMeta] = []
    for name, base in zip(names, originals):
        row = table.get(_key(name)) or table.get(_key(base))
        series = (row.series if row is not None and row.series else "") or infer_series(base)
        group = (row.group if row is not None and row.group else "") \
            or (folder_labels.get(name, "") if folder_ok else "") or infer_class(base) or DEFAULT_CLASS
        result.append(SampleMeta(name, series, group))
    return result


class GcmsAnalyzer:
    """Menjalankan analisis GC-MS lengkap sesuai ``GcmsConfig``."""

    def __init__(self, config: GcmsConfig, logger: Optional[logging.Logger] = None) -> None:
        self.cfg = config
        self.log = logger or logging.getLogger("chemflow.gcms")

    # ------------------------------------------------------------ alur utama

    def run(self) -> GcmsResult:
        cfg = self.cfg
        cfg.gcms_dir.mkdir(parents=True, exist_ok=True)
        dataset = read_data(cfg.data, rt_unit=cfg.rt_unit, exclude_dirs=[cfg.gcms_dir], logger=self.log)
        groups_table = read_groups_table(cfg.groups_file) if cfg.groups_file else None
        names = [c.name for c in dataset.chromatograms] if dataset.chromatograms else list(dataset.table.samples)
        originals = [c.meta.get("original_name", c.name) for c in dataset.chromatograms] or names
        meta = assign_metadata(names, dataset.folder_labels, groups_table, self.log, originals)
        if len(names) < 2:
            self.log.warning("Hanya satu sampel: analisis perbandingan (PCA, HCA, statistik) dilewati; "
                             "puncak dan kromatogram tetap diproses.")
        for chrom, m in zip(dataset.chromatograms, meta):
            chrom.series, chrom.group = m.series, m.group

        result = GcmsResult(
            samples=pd.DataFrame({"sample": [m.name for m in meta], "series": [m.series for m in meta],
                                  "class": [m.group for m in meta]}),
            features=pd.DataFrame(),
        )
        if dataset.table is not None:
            work = self._from_table(dataset.table, meta, result)
        else:
            work = self._from_signals(dataset, meta, result)
        self._identify(work, result)
        self._compare(work, meta, result)
        self._write(work, meta, result)
        self._save_config()
        return result

    # ------------------------------------------------------------ tahap data

    def _from_table(self, table: FeatureTable, meta: List[SampleMeta], result: GcmsResult) -> Dict[str, Any]:
        self.log.info(f"Tabel fitur: {len(table.samples)} sampel x {len(table.features)} fitur "
                      f"(tanpa pemrosesan sinyal).")
        rts = np.array([_rt_from_label(f) for f in table.features])
        names = ["" if np.isfinite(rt) else str(f) for f, rt in zip(table.features, rts)]
        return {"raw": table.values, "features": list(table.features), "rt": rts, "names": names,
                "cas": [""] * len(table.features), "signals": None, "peaks": None, "chroms": [], "bins": None}

    def _from_signals(self, dataset: GcmsDataset, meta: List[SampleMeta], result: GcmsResult) -> Dict[str, Any]:
        cfg = self.cfg
        chroms = dataset.chromatograms
        with_signal = [c for c in chroms if c.has_signal]
        if not with_signal:
            return self._from_peak_tables(chroms, result)
        if len(with_signal) < len(chroms):
            missing = [c.name for c in chroms if not c.has_signal]
            raise ValueError(f"Sebagian sampel hanya berisi tabel puncak tanpa sinyal ({', '.join(missing[:4])}); "
                             f"pisahkan kelompok data ini atau sediakan kromatogram untuk semua sampel.")
        grid = proc.common_grid(chroms, cfg.rt_range)
        self.log.info(f"{len(chroms)} kromatogram, rentang {grid[0]:.2f} sampai {grid[-1]:.2f} menit, "
                      f"{grid.size} titik (selang {60 * (grid[1] - grid[0]):.2f} detik).")
        raw = np.array([proc.resample(c, grid) for c in chroms])
        corrected, baselines = [], []
        for y in raw:
            c, b = proc.preprocess(grid, y, baseline=cfg.baseline, smooth_minutes=cfg.smooth_window)
            corrected.append(c)
            baselines.append(b)
        corrected, baselines = np.array(corrected), np.array(baselines)
        before = corrected.copy()
        shifts = np.zeros(len(chroms))
        if cfg.align and len(chroms) > 1:
            corrected, shifts = proc.align_signals(grid, corrected, cfg.max_shift)
            self.log.info(f"RT diselaraskan; pergeseran terbesar {np.abs(shifts).max() * 60:.1f} detik.")
        peak_lists = [proc.detect_peaks(grid, y, cfg.min_snr, cfg.min_prominence) for y in corrected]
        for chrom, peaks in zip(chroms, peak_lists):
            self._inherit_names(peaks, chrom.peaks)
        self.log.info("Puncak terdeteksi per sampel: " + ", ".join(f"{c.name}={len(p)}" for c, p in zip(chroms, peak_lists)))
        centers, bins = proc.bin_matrix(grid, corrected, cfg.bin_width)
        if cfg.feature_mode == "bins":
            self.log.info(f"Fitur = sidik jari kromatogram: {bins.shape[1]} bin selebar {cfg.bin_width:g} menit.")
            areas, heights, rts, names = bins, bins.copy(), centers, [""] * len(centers)
        else:
            areas, heights, rts, names = proc.peak_feature_matrix(grid, corrected, peak_lists, cfg.peak_tolerance,
                                                                  cfg.min_presence, True, cfg.min_snr)
        cas = [""] * len(rts)
        return {"grid": grid, "raw_signal": raw, "baseline": baselines, "signals": corrected, "before": before,
                "shifts": shifts, "peaks": peak_lists, "chroms": chroms, "raw": areas, "heights": heights, "rt": rts,
                "names": names, "cas": cas, "features": [f"{rt:.3f}" for rt in rts], "bins": bins, "bin_rt": centers}

    def _from_peak_tables(self, chroms: List[Chromatogram], result: GcmsResult) -> Dict[str, Any]:
        cfg = self.cfg
        peak_lists = [c.peaks for c in chroms]
        if not any(peak_lists):
            raise ValueError("Tidak ada sinyal maupun puncak yang bisa diproses.")
        clusters = [c for c in proc.cluster_peaks(peak_lists, cfg.peak_tolerance)
                    if len(c) / len(chroms) >= cfg.min_presence]
        areas = np.zeros((len(chroms), len(clusters)))
        rts, names, cas = np.zeros(len(clusters)), [], []
        for j, cluster in enumerate(clusters):
            rts[j] = float(np.median([p.rt for _, p in cluster]))
            for sample, peak in cluster:
                areas[sample, j] = peak.area if peak.area > 0 else peak.height
            labels = [p.name for _, p in cluster if p.name]
            codes = [p.cas for _, p in cluster if p.cas]
            names.append(max(set(labels), key=labels.count) if labels else "")
            cas.append(max(set(codes), key=codes.count) if codes else "")
        self.log.info(f"Hanya tabel puncak (tanpa sinyal): {len(clusters)} fitur selaras; deteksi puncak, "
                      f"koreksi baseline, dan sidik jari bin dilewati.")
        return {"signals": None, "peaks": peak_lists, "chroms": chroms, "raw": areas, "heights": areas.copy(), "rt": rts,
                "names": names, "cas": cas, "features": [f"{rt:.3f}" for rt in rts], "bins": None}

    @staticmethod
    def _inherit_names(detected: List[Peak], reported: Sequence[Peak]) -> None:
        """Salin nama, CAS, dan skor kemiripan dari laporan instrumen ke puncak hasil deteksi yang RT-nya berdekatan."""
        for peak in detected:
            best = min(reported, key=lambda r: abs(r.rt - peak.rt), default=None)
            if best is not None and abs(best.rt - peak.rt) <= 0.03:
                peak.name, peak.cas, peak.similarity = best.name, best.cas, best.similarity

    def _identify(self, work: Dict[str, Any], result: GcmsResult) -> None:
        """Beri nama fitur lewat pustaka pengguna (RT atau RI), laporan instrumen, dan tabel alergen."""
        cfg = self.cfg
        rts = np.asarray(work["rt"], dtype=float)
        names = list(work["names"])
        cas = list(work["cas"])
        smiles = [""] * len(rts)
        source = ["laporan instrumen" if n else "" for n in names]
        ri = np.full(len(rts), np.nan)
        if cfg.alkanes:
            carbons, alkane_rt = lib.load_alkanes(cfg.alkanes)
            ri = lib.kovats_index(rts, carbons, alkane_rt)
            self.log.info(f"Indeks Kovats dihitung dari deret alkana C{int(carbons.min())} sampai C{int(carbons.max())}.")
        if cfg.library:
            compounds = lib.load_library(cfg.library)
            for index, (compound, delta) in lib.match_by_retention(
                    rts, ri if cfg.alkanes else None, compounds, cfg.rt_tolerance, cfg.ri_tolerance).items():
                names[index], cas[index], smiles[index], source[index] = compound.name, compound.cas, compound.smiles, "pustaka pengguna"
            self.log.info(f"Pustaka pengguna: {sum(s == 'pustaka pengguna' for s in source)} dari {len(rts)} fitur bernama.")
        allergens = lib.match_by_name(names, cas)
        for index, compound in allergens.items():
            if not smiles[index]:
                smiles[index] = compound.smiles
            if not cas[index]:
                cas[index] = compound.cas
        work.update(names=names, cas=cas, smiles=smiles, source=source, ri=ri, allergens=allergens)
        if not any(names):
            result.notes.append("Tidak ada fitur bernama: berikan --gcms-library (RT atau RI standar) atau laporan "
                                "puncak instrumen agar senyawa dan alergen dapat diidentifikasi.")
            self.log.info(result.notes[-1])

    # ------------------------------------------------------------ statistik

    def _labels(self, meta: List[SampleMeta]) -> Tuple[List[str], str]:
        """Label kelompok untuk statistik dan penandaan: kelas bila minimal dua, kalau tidak seri."""
        classes = [m.group for m in meta]
        series = [m.series for m in meta]
        mode = self.cfg.label_by
        if mode == "auto":
            mode = "class" if len(set(classes)) >= 2 else "series"
        return (classes, "class") if mode == "class" else (series, "series")

    def _compare(self, work: Dict[str, Any], meta: List[SampleMeta], result: GcmsResult) -> None:
        cfg = self.cfg
        raw = np.asarray(work["raw"], dtype=float)
        normalized = proc.normalize_rows(raw, cfg.normalization)
        keep = normalized.std(axis=0) > 0
        if keep.sum() < normalized.shape[1]:
            self.log.info(f"{int((~keep).sum())} fitur konstan dibuang sebelum statistik.")
        work["norm"] = normalized
        work["keep"] = keep
        work["model_matrix"] = proc.transform_values(normalized, cfg.transform)
        work["labels"], work["label_kind"] = self._labels(meta)
        labels = work["labels"]
        n = len(meta)
        result.tables["pca_scores"] = pd.DataFrame()
        if n < 2:
            return
        X = work["model_matrix"][:, keep]
        feature_names = [f for f, k in zip(self._feature_labels(work), keep) if k]
        rts = np.asarray(work["rt"])[keep]
        work["model_features"], work["model_rt"] = feature_names, rts

        self._pca(work, X, feature_names, meta, result)
        self._hca(work, X, meta, result)
        self._similarity(work, meta, result)
        self._supervised(work, X, feature_names, meta, labels, result)
        self._univariate(work, X, feature_names, labels, keep, result)
        self._outliers(work, result)

    def _feature_labels(self, work: Dict[str, Any]) -> List[str]:
        labels = []
        for rt, name, feature in zip(work["rt"], work["names"], work["features"]):
            base = f"{rt:.2f}" if np.isfinite(rt) else str(feature)
            labels.append(f"{name} ({base})" if name else base)
        return labels

    def _pca(self, work, X, feature_names, meta, result) -> None:
        cfg = self.cfg
        classes, series = [m.group for m in meta], [m.series for m in meta]
        # Penanda mengikuti kelas; warna mengikuti seri. Tanpa dua kelas, seri menjadi penanda sekaligus warna.
        groups, colors = (classes, series) if len(set(classes)) >= 2 else (series, None)
        if colors is not None and len(set(colors)) < 2:
            colors = None
        try:
            pca = ChemometricPCA(logger=self.log)
            work["pca"] = pca.compute(X.tolist(), feature_names, [m.name for m in meta], groups, n_components=3,
                                      series=colors, scaling=cfg.scaling)
            work["pca_engine"] = pca
        except ValueError as exc:
            self.log.info(f"PCA dilewati: {exc}")
            result.notes.append(f"PCA dilewati: {exc}")
            return
        pca_result: PcaResult = work["pca"]
        table = pd.DataFrame(pca_result.scores, columns=[f"PC{i + 1}" for i in range(pca_result.n_components)])
        table.insert(0, "class", classes)
        table.insert(0, "series", series)
        table.insert(0, "sample", [m.name for m in meta])
        result.tables["pca_scores"] = table
        loadings = pd.DataFrame(pca_result.loadings, columns=[f"PC{i + 1}" for i in range(pca_result.n_components)])
        loadings.insert(0, "rt_min", work["model_rt"])
        loadings.insert(0, "feature", feature_names)
        result.tables["pca_loadings"] = loadings
        result.tables["pca_variance"] = pd.DataFrame({
            "component": [f"PC{i + 1}" for i in range(pca_result.n_components)],
            "variance_percent": [v * 100 for v in pca_result.explained_variance_ratio],
            "cumulative_percent": np.cumsum(pca_result.explained_variance_ratio) * 100})

    def _hca(self, work, X, meta, result) -> None:
        if len(meta) < 3:
            return
        hca = HierarchicalClustering(logger=self.log)
        work["hca"] = hca.compute(X.tolist(), [m.name for m in meta], [m.series for m in meta])
        work["hca_engine"] = hca

    def _similarity(self, work, meta, result) -> None:
        basis = work["bins"] if work.get("bins") is not None else work["norm"]
        names = [m.name for m in meta]
        cosine = stats.similarity_matrix(basis, names, "cosine")
        pearson = stats.similarity_matrix(basis, names, "pearson")
        result.tables["similarity_cosine"] = cosine.reset_index(names="sample")
        result.tables["similarity_pearson"] = pearson.reset_index(names="sample")
        work["cosine"], work["pearson"] = cosine, pearson
        work["similarity_basis"] = "bin waktu" if work.get("bins") is not None else "fitur puncak"

    def _supervised(self, work, X, feature_names, meta, labels, result) -> None:
        cfg = self.cfg
        reason = stats.supervised_blocker(labels)
        work["classifiers"] = []
        if reason:
            note = f"Model terawasi (PLS-DA, LDA) dilewati: {reason}."
            self.log.info(note)
            result.notes.append(note)
            return
        rows = []
        for runner in (stats.pls_da, stats.lda_cv):
            try:
                outcome = runner(X, labels, scaling=cfg.scaling, n_permutations=cfg.n_permutations, seed=cfg.seed)
            except ValueError as exc:
                self.log.info(str(exc))
                continue
            work["classifiers"].append(outcome)
            rows.append({"metode": outcome.method, "komponen": outcome.n_components, "lipatan_CV": outcome.n_splits,
                         "akurasi_CV_persen": outcome.accuracy * 100, "akurasi_seimbang_persen": outcome.balanced_accuracy * 100,
                         "Q2": outcome.q2, "p_permutasi": outcome.permutation_p, "n_permutasi": outcome.n_permutations})
            result.tables[f"konfusi_{outcome.method}"] = outcome.confusion.reset_index(names="kelas_sebenarnya")
        if rows:
            result.tables["klasifikasi"] = pd.DataFrame(rows)
        pls = next((c for c in work["classifiers"] if c.method == "PLS-DA"), None)
        if pls is not None and pls.vip is not None:
            work["vip"] = pls.vip
            table = pd.DataFrame({"feature": feature_names, "rt_min": work["model_rt"], "vip": pls.vip})
            result.tables["vip"] = table.sort_values("vip", ascending=False).reset_index(drop=True)

    def _univariate(self, work, X, feature_names, labels, keep, result) -> None:
        classes = sorted(set(labels))
        if len(classes) < 2 or min(labels.count(c) for c in classes) < 2:
            self.log.info("Uji univariat dilewati: butuh minimal dua kelompok dengan dua sampel atau lebih.")
            return
        raw = np.asarray(work["norm"])[:, keep]
        table = stats.univariate_tests(X, labels, feature_names, raw=raw)
        table.insert(1, "rt_min", work["model_rt"])
        p_columns = [c for c in table.columns if c.startswith("q_")]
        if "vip" in work:
            table["vip"] = work["vip"]
        table = table.sort_values(p_columns[0] if p_columns else "feature").reset_index(drop=True)
        result.tables["univariat"] = table
        work["univariate"] = table
        work["classes"] = classes
        signif = int((table[p_columns[0]] < 0.05).sum()) if p_columns else 0
        self.log.info(f"Uji univariat: {signif} dari {len(table)} fitur signifikan (q < 0,05).")

    def _outliers(self, work, result) -> None:
        pca = work.get("pca")
        if pca is None or pca.scores.shape[0] <= pca.n_components + 1:
            return
        table = stats.hotelling_t2(pca.scores, pca.labels)
        result.tables["pencilan_T2"] = table
        flagged = table.loc[table["outlier"], "sample"].tolist()
        if flagged:
            self.log.warning(f"Pencilan T2 Hotelling (95%): {', '.join(flagged)}")

    # ------------------------------------------------------------ keluaran

    def _write(self, work: Dict[str, Any], meta: List[SampleMeta], result: GcmsResult) -> None:
        cfg = self.cfg
        feature_table = self._feature_frame(work, meta)
        result.features = feature_table
        peaks_table = self._peaks_frame(work, meta)
        if not peaks_table.empty:
            result.tables["puncak"] = peaks_table
        self._allergen_table(work, meta, result)
        result.tables["fitur_selaras"] = feature_table
        if "shifts" in work:
            result.samples["geser_RT_detik"] = work["shifts"] * 60.0
        if work.get("peaks"):
            result.samples["jumlah_puncak"] = [len(p) for p in work["peaks"]]
            result.samples["total_area"] = [sum(p.area for p in peaks) for peaks in work["peaks"]]
        if work.get("chroms"):
            result.samples["sumber"] = [c.source for c in work["chroms"]]
        result.samples["label_statistik"] = work.get("labels", [m.group for m in meta])
        if cfg.make_plots:
            self._plots(work, meta, result)
        result.ligands_file = self._ligands_file(work, meta)
        result.workbook = self._workbook(result, meta)
        self.log.info(f"Hasil GC-MS: {result.workbook}")

    def _feature_frame(self, work, meta) -> pd.DataFrame:
        cfg = self.cfg
        norm = np.asarray(work["norm"])
        data: Dict[str, Any] = {"fitur": self._feature_labels(work), "rt_min": work["rt"], "nama": work["names"],
                                "cas": work["cas"], "smiles": work.get("smiles", [""] * len(work["rt"])),
                                "sumber_nama": work.get("source", [""] * len(work["rt"]))}
        if "ri" in work and np.isfinite(np.asarray(work["ri"])).any():
            data["ri_kovats"] = work["ri"]
        frame = pd.DataFrame(data)
        for i, m in enumerate(meta):
            frame[f"{m.name} [{cfg.normalization}]"] = norm[i]
        return frame

    def _peaks_frame(self, work, meta) -> pd.DataFrame:
        rows = []
        for m, peaks in zip(meta, work.get("peaks") or []):
            for k, p in enumerate(sorted(peaks, key=lambda item: item.rt), start=1):
                rows.append({"sample": m.name, "peak": k, "rt_min": p.rt, "start_min": p.start, "end_min": p.end,
                             "height": p.height, "area": p.area, "area_percent": p.area_pct, "snr": p.snr,
                             "name": p.name, "cas": p.cas, "similarity": p.similarity})
        return pd.DataFrame(rows)

    def _allergen_table(self, work, meta, result) -> None:
        allergens = work.get("allergens") or {}
        if not allergens:
            return
        norm = np.asarray(work["norm"])
        rows = []
        for index, compound in allergens.items():
            row = {"alergen": compound.name, "cas": compound.cas, "rt_min": work["rt"][index],
                   "nama_terdeteksi": work["names"][index]}
            for i, m in enumerate(meta):
                row[m.name] = float(norm[i, index])
            rows.append(row)
        table = pd.DataFrame(rows).sort_values("alergen").reset_index(drop=True)
        result.tables["alergen"] = table
        work["allergen_table"] = table
        self.log.info(f"Alergen wewangian terdeteksi (dugaan): {len(table)}. Nilai adalah persen luas puncak, "
                      f"bukan konsentrasi; ambang label UE (0,001 % leave-on, 0,01 % rinse-off) butuh kuantifikasi standar.")

    def _plots(self, work, meta, result) -> None:
        cfg = self.cfg
        plotter = GcmsPlotter(cfg.dpi, cfg.figure_formats)
        directory = cfg.plots_dir
        names = [m.name for m in meta]
        series = [m.series for m in meta]

        def add(path: Optional[Path]) -> None:
            if path is not None:
                result.plots.append(Path(path))

        try:
            self._signal_plots(work, meta, plotter, directory, add, names, series)
            pca: Optional[PcaResult] = work.get("pca")
            engine: Optional[ChemometricPCA] = work.get("pca_engine")
            if pca is not None and engine is not None:
                add(engine.plot_2d(pca, directory / "pca_2d.png", title="PCA GC-MS (2D)", dpi=cfg.dpi,
                                   formats=cfg.figure_formats, show_loadings=False))
                added = engine.plot_3d(pca, directory / "pca_3d.png", title="PCA GC-MS (3D)", dpi=cfg.dpi, formats=cfg.figure_formats)
                add(added)
                add(plotter.scree_plot(pca.explained_variance_ratio, directory / "pca_variansi.png"))
                add(plotter.loadings_plot(np.asarray(work["model_rt"]), pca.loadings, pca.explained_variance_ratio,
                                          directory / "pca_loading_rt.png"))
            hca = work.get("hca")
            if hca is not None:
                paths = work["hca_engine"].plot_dendrogram(hca, directory / "hca_dendrogram.png", title="HCA sampel GC-MS",
                                                           dpi=cfg.dpi, formats=cfg.figure_formats)
                for path in paths:
                    add(path)
            self._heatmap_plot(work, meta, plotter, directory, add)
            if "cosine" in work:
                basis = work["similarity_basis"]
                add(plotter.similarity_heatmap(work["cosine"], directory / "kemiripan_kosinus.png",
                                               f"Kemiripan kosinus antar sampel ({basis})"))
            self._group_plots(work, meta, plotter, directory, add)
            self._classification_plots(work, plotter, directory, add)
            table = work.get("allergen_table")
            if table is not None and not table.empty:
                add(plotter.allergen_plot(table.set_index("alergen")[names], directory / "alergen.png"))
        except Exception as exc:  # grafik tidak boleh menggagalkan tabel hasil
            self.log.warning(f"Sebagian grafik gagal dibuat: {exc}")
            result.notes.append(f"Sebagian grafik gagal dibuat: {exc}")

    def _signal_plots(self, work, meta, plotter, directory, add, names, series) -> None:
        if work.get("signals") is None:
            return
        grid, signals = work["grid"], work["signals"]
        add(plotter.chromatogram_overlay(grid, signals, names, series, directory / "kromatogram_tumpang_tindih.png",
                                         "Kromatogram TIC terkoreksi baseline dan diselaraskan"))
        if len(names) > 1 and self.cfg.align:
            add(plotter.alignment_check(grid, work["before"], signals, work["shifts"], names,
                                        directory / "penyelarasan_rt.png"))
        add(plotter.peak_summary(names, [len(p) for p in work["peaks"]],
                                 [sum(p.area for p in peaks) for peaks in work["peaks"]], series,
                                 directory / "ringkasan_puncak.png"))
        for i, m in enumerate(meta[:MAX_ANNOTATED_SAMPLES]):
            safe = re.sub(r"[^\w\-]+", "_", m.name)
            add(plotter.annotated_chromatogram(grid, work["raw_signal"][i], work["baseline"][i], signals[i],
                                               work["peaks"][i], m.name, directory / f"kromatogram_{safe}.png"))

    def _heatmap_plot(self, work, meta, plotter, directory, add) -> None:
        X = work.get("model_matrix")
        if X is None or len(meta) < 2:
            return
        keep = work["keep"]
        top = min(self.cfg.top_features, int(keep.sum()))
        if top < 2:
            return
        matrix = X[:, keep]
        if "vip" in work:
            order = np.argsort(work["vip"])[::-1][:top]
        else:
            order = np.argsort(matrix.var(axis=0))[::-1][:top]
        labels = [work["model_features"][i] for i in order]
        add(plotter.clustered_heatmap(matrix[:, order], [m.name for m in meta], labels, [m.series for m in meta],
                                      directory / "peta_panas_fitur.png",
                                      f"{top} fitur teratas ({'VIP' if 'vip' in work else 'variansi'})"))

    def _group_plots(self, work, meta, plotter, directory, add) -> None:
        grid, signals = work.get("grid"), work.get("signals")
        if signals is None or len(meta) < 2:
            return
        labels = work["labels"]
        classes = sorted(set(labels), key=labels.index)
        if len(classes) < 2:
            return
        means = {c: signals[[i for i, l in enumerate(labels) if l == c]].mean(axis=0) for c in classes}
        pairs = [(a, b) for i, a in enumerate(classes) for b in classes[i + 1:]][:6]
        for a, b in pairs:
            cosine = float(np.dot(means[a], means[b]) / max(np.linalg.norm(means[a]) * np.linalg.norm(means[b]), 1e-12))
            safe = re.sub(r"[^\w\-]+", "_", f"{a}_vs_{b}")
            add(plotter.mirror_plot(grid, means[a], means[b], a, b, cosine, directory / f"cermin_{safe}.png"))

    def _classification_plots(self, work, plotter, directory, add) -> None:
        for outcome in work.get("classifiers", []):
            tag = outcome.method.lower().replace("-", "")
            add(plotter.confusion_plot(outcome, directory / f"konfusi_{tag}.png"))
            add(plotter.permutation_plot(outcome, directory / f"permutasi_{tag}.png"))
            if outcome.method == "PLS-DA" and outcome.scores is not None and outcome.scores.shape[1] >= 2:
                width = min(3, outcome.scores.shape[1])
                scores = PcaResult(scores=outcome.scores[:, :width], explained_variance_ratio=tuple(outcome.explained_x[:width]),
                                   loadings=np.zeros((1, width)), feature_names=[],
                                   labels=[str(i + 1) for i in range(len(work["labels"]))],
                                   groups=list(work["labels"]), axis_prefix="LV")
                add(work["pca_engine"].plot_2d(scores, directory / "plsda_skor.png", title="Skor PLS-DA",
                                               dpi=self.cfg.dpi, formats=self.cfg.figure_formats, show_loadings=False,
                                               annotate=False))
            if outcome.vip is not None:
                names = work["model_features"]
                favored = self._favored_group(work)
                add(plotter.vip_plot(names, outcome.vip, favored, directory / "vip.png"))
        table = work.get("univariate")
        if table is not None and len(work.get("classes", [])) == 2:
            add(plotter.volcano(table, work["classes"], directory / "volcano.png"))

    def _favored_group(self, work) -> List[str]:
        labels = np.asarray(work["labels"])
        matrix = np.asarray(work["norm"])[:, work["keep"]]
        classes = sorted(set(labels))
        means = np.array([matrix[labels == c].mean(axis=0) for c in classes])
        return [classes[i] for i in means.argmax(axis=0)]

    def _ligands_file(self, work, meta) -> Optional[Path]:
        smiles, names = work.get("smiles"), work["names"]
        if smiles is None:
            return None
        rows = []
        norm = np.asarray(work["norm"])
        for j, (name, smi) in enumerate(zip(names, smiles)):
            if name and smi:
                dominant = meta[int(np.argmax(norm[:, j]))].series
                rows.append({"name": name, "smiles": smi, "group": dominant})
        if not rows:
            return None
        frame = pd.DataFrame(rows).drop_duplicates(subset="name")
        path = self.cfg.gcms_dir / "ligan_gcms.xlsx"
        frame.to_excel(path, index=False)
        from chemflow.utils.excel_utils import autofit_columns
        autofit_columns(path)
        self.log.info(f"{len(frame)} senyawa bernama dengan SMILES ditulis ke {path.name} (bisa dipakai sebagai "
                      f"--ligands untuk docking).")
        return path

    def _workbook(self, result: GcmsResult, meta: List[SampleMeta]) -> Path:
        cfg = self.cfg
        path = cfg.gcms_dir / "analisis_gcms.xlsx"
        parameters = pd.DataFrame(
            [(k, ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else ("" if v is None else v))
             for k, v in cfg.to_dict().items()], columns=["parameter", "nilai"])
        order = ["puncak", "fitur_selaras", "univariat", "vip", "klasifikasi", "pca_variance", "pca_scores",
                 "pca_loadings", "similarity_cosine", "similarity_pearson", "pencilan_T2", "alergen"]
        titles = {"puncak": "Puncak", "fitur_selaras": "Fitur Selaras", "univariat": "Uji Univariat", "vip": "VIP PLS-DA",
                  "klasifikasi": "Klasifikasi", "pca_variance": "PCA Variansi", "pca_scores": "PCA Skor",
                  "pca_loadings": "PCA Loading", "similarity_cosine": "Kemiripan Kosinus",
                  "similarity_pearson": "Kemiripan Pearson", "pencilan_T2": "Pencilan T2", "alergen": "Alergen"}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            result.samples.to_excel(writer, sheet_name="Sampel", index=False)
            for key in order:
                table = result.tables.get(key)
                if table is not None and not table.empty:
                    table.to_excel(writer, sheet_name=titles[key], index=False)
            for key, table in result.tables.items():
                if key.startswith("konfusi_") and not table.empty:
                    table.to_excel(writer, sheet_name=f"Konfusi {key.split('_', 1)[1]}"[:31], index=False)
            notes = pd.DataFrame({"catatan": result.notes or ["Tidak ada catatan."]})
            notes.to_excel(writer, sheet_name="Catatan", index=False)
            parameters.to_excel(writer, sheet_name="Parameter", index=False)
        from chemflow.utils.excel_utils import autofit_columns
        autofit_columns(path)
        return path

    def _save_config(self) -> None:
        (self.cfg.gcms_dir / CONFIG_FILENAME).write_text(
            json.dumps(self.cfg.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def _rt_from_label(text: str) -> float:
    """RT (menit) bila seluruh label fitur adalah angka ("12,34", "RT 12.34 min"), selain itu NaN (label berupa nama)."""
    match = re.fullmatch(r"\s*(?:rt\s*)?(\d+(?:[.,]\d+)?)\s*(?:min)?\s*", str(text).lower())
    return float(match.group(1).replace(",", ".")) if match else float("nan")


def load_saved_config(output_dir: "str | Path") -> Optional[GcmsConfig]:
    """Konfigurasi GC-MS yang tersimpan dari analisis sebelumnya pada folder run, atau ``None``."""
    path = Path(output_dir) / GCMS_DIRNAME / CONFIG_FILENAME
    if not path.is_file():
        return None
    return GcmsConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))


def run_gcms_analysis(config: GcmsConfig, logger: Optional[logging.Logger] = None) -> GcmsResult:
    """Jalankan analisis GC-MS lengkap dan kembalikan hasilnya."""
    return GcmsAnalyzer(config, logger).run()
