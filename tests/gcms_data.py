"""Pembuat data GC-MS sintetis untuk tes: kromatogram Gaussian dengan derau dan berkas berbagai format."""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

# (rt menit, tinggi, sigma menit)
PeakSpec = Tuple[float, float, float]
COMMON_PEAKS: List[PeakSpec] = [
    (6.0, 4.0e5, 0.02), (7.5, 9.0e5, 0.025), (8.0, 6.0e5, 0.02), (9.5, 1.2e6, 0.03), (11.0, 5.0e5, 0.02),
    (12.0, 3.0e5, 0.02), (13.5, 8.0e5, 0.025), (15.2, 7.0e5, 0.03), (17.0, 4.5e5, 0.02), (19.0, 9.5e5, 0.03),
]


def synthetic_peaks(scale: Dict[float, float] = None, extra: Sequence[PeakSpec] = ()) -> List[PeakSpec]:
    """COMMON_PEAKS dengan tinggi diskalakan per RT (``scale``) ditambah puncak ekstra."""
    scale = scale or {}
    return [(rt, h * scale.get(rt, 1.0), s) for rt, h, s in COMMON_PEAKS] + list(extra)


def make_trace(peaks: Sequence[PeakSpec], rt_start: float = 5.0, rt_end: float = 21.0, step: float = 0.005,
               noise: float = 300.0, drift: float = 2.0e4, jitter: float = 0.0, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """(rt, intensitas): puncak Gaussian, baseline miring, derau normal, dan pergeseran RT seragam ``jitter``."""
    rng = np.random.default_rng(seed)
    rt = np.arange(rt_start, rt_end, step)
    signal = drift * (rt - rt_start) / (rt_end - rt_start) + 1.0e3
    for center, height, sigma in peaks:
        signal += height * np.exp(-0.5 * ((rt - center - jitter) / sigma) ** 2)
    return rt, signal + rng.normal(0.0, noise, rt.size)


def gaussian_area(height: float, sigma: float) -> float:
    return height * sigma * np.sqrt(2.0 * np.pi)


def write_shimadzu_text(path: Path, rt: np.ndarray, y: np.ndarray, peaks: Sequence[Tuple[float, float, float, str]] = (),
                        rt_factor: float = 1.0, delimiter: str = "\t", event_msec: float = None) -> Path:
    """Ekspor gaya GCMSsolution: bagian [Header], [MS Chromatogram], dan opsional [MS Peak Table].

    ``rt_factor`` 1000 meniru RT menit yang terkali 1000 akibat pemisah desimal lokal.
    """
    event_msec = event_msec if event_msec is not None else float(np.median(np.diff(rt)) * 60000.0)
    rows = [["[Header]"], ["Data File Name", f"C:\\Data\\{path.stem}.qgd"], ["Output Date", "2026-09-20"], [],
            ["[MS Chromatogram]"], ["m/z", "1-1 TIC"], ["Event Time(msec)", f"{event_msec:g}"],
            ["# of Points", str(rt.size)], ["Start Time(min)", f"{rt[0] * rt_factor:g}"],
            ["End Time(min)", f"{rt[-1] * rt_factor:g}"], ["Ret.Time", "Absolute Intensity", "Relative Intensity"]]
    top = float(y.max()) or 1.0
    rows += [[f"{r * rt_factor:.6g}", f"{v:.1f}", f"{100 * v / top:.2f}"] for r, v in zip(rt, y)]
    if peaks:
        rows += [[], ["[MS Peak Table]"], ["Peak#", "R.Time", "I.Time", "F.Time", "Area", "Area%", "Height", "Height%", "Name"]]
        for k, (peak_rt, area, height, name) in enumerate(peaks, start=1):
            rows.append([str(k), f"{peak_rt * rt_factor:.6g}", f"{(peak_rt - 0.05) * rt_factor:.6g}",
                         f"{(peak_rt + 0.05) * rt_factor:.6g}", f"{area:.0f}", "1.0", f"{height:.0f}", "1.0", name])
    path.write_text("\n".join(delimiter.join(row) for row in rows) + "\n", encoding="utf-8")
    return path


def write_two_column_csv(path: Path, rt: np.ndarray, y: np.ndarray, header: Sequence[str] = ("Time (min)", "Intensity"),
                         delimiter: str = ",", decimal: str = ".") -> Path:
    lines = [] if header is None else [delimiter.join(header)]
    lines += [delimiter.join((f"{r:.4f}".replace(".", decimal), f"{v:.1f}".replace(".", decimal))) for r, v in zip(rt, y)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_mzml(path: Path, rt: np.ndarray, y: np.ndarray, tic_chromatogram: bool = False, compress: bool = True) -> Path:
    """mzML minimal: spektrum MS1 dengan larik m/z dan intensitas (TIC dihitung pembaca) atau kromatogram TIC."""
    def array(values: np.ndarray, accession: str, name: str) -> str:
        raw = np.asarray(values, dtype="<f8").tobytes()
        raw = zlib.compress(raw) if compress else raw
        codec = "MS:1000574" if compress else "MS:1000576"
        return (f'<binaryDataArray encodedLength="{len(raw)}"><cvParam accession="MS:1000523" name="64-bit float"/>'
                f'<cvParam accession="{codec}" name="compression"/><cvParam accession="{accession}" name="{name}"/>'
                f'<binary>{base64.b64encode(raw).decode()}</binary></binaryDataArray>')

    if tic_chromatogram:
        body = ('<chromatogramList count="1"><chromatogram id="TIC"><binaryDataArrayList count="2">'
                + array(rt, "MS:1000595", "time array") + array(y, "MS:1000515", "intensity array")
                + '</binaryDataArrayList></chromatogram></chromatogramList>')
        run = f'<run><spectrumList count="0"></spectrumList>{body}</run>'
    else:
        spectra = []
        for index, (r, v) in enumerate(zip(rt, y)):
            spectra.append(
                f'<spectrum index="{index}" id="scan={index}" defaultArrayLength="2"><cvParam accession="MS:1000511" name="ms level" value="1"/>'
                f'<scanList count="1"><scan><cvParam accession="MS:1000016" name="scan start time" value="{r}" unitName="minute"/></scan></scanList>'
                f'<binaryDataArrayList count="2">{array(np.array([50.0, 100.0]), "MS:1000514", "m/z array")}'
                f'{array(np.array([v / 2, v / 2]), "MS:1000515", "intensity array")}</binaryDataArrayList></spectrum>')
        run = f'<run><spectrumList count="{len(rt)}">{"".join(spectra)}</spectrumList></run>'
    path.write_text(f'<?xml version="1.0"?><mzML xmlns="http://psi.hupo.org/ms/mzml">{run}</mzML>', encoding="utf-8")
    return path


def write_mzxml(path: Path, rt: np.ndarray, y: np.ndarray, with_tic_attribute: bool = True) -> Path:
    scans = []
    for index, (r, v) in enumerate(zip(rt, y), start=1):
        peaks = base64.b64encode(zlib.compress(struct.pack(">4f", 50.0, v / 2, 100.0, v / 2))).decode()
        tic = f' totIonCurrent="{v}"' if with_tic_attribute else ""
        scans.append(f'<scan num="{index}" msLevel="1" retentionTime="PT{r * 60:.4f}S"{tic}>'
                     f'<peaks precision="32" byteOrder="network" compressionType="zlib" pairOrder="m/z-int">{peaks}</peaks></scan>')
    path.write_text('<?xml version="1.0"?><mzXML xmlns="http://sashimi.sourceforge.net/schema_revision/mzXML_3.2">'
                    f'<msRun scanCount="{len(rt)}">{"".join(scans)}</msRun></mzXML>', encoding="utf-8")
    return path


def write_cdf(path: Path, rt: np.ndarray, y: np.ndarray) -> Path:
    """ANDI-MS netCDF klasik dengan waktu dalam detik dan total_intensity."""
    from scipy.io import netcdf_file

    with netcdf_file(str(path), "w") as nc:
        nc.createDimension("scan_number", rt.size)
        times = nc.createVariable("scan_acquisition_time", "d", ("scan_number",))
        times[:] = rt * 60.0
        total = nc.createVariable("total_intensity", "d", ("scan_number",))
        total[:] = y
        nc.experiment_title = b"synthetic"
    return path


def build_study(root: Path, seed: int = 1) -> Dict[str, Path]:
    """Studi 2 kelas (Asli, Tiruan) x 2 seri (Melati, Mawar) x 3 ulangan sebagai CSV dua kolom, satu folder per kelas.

    Tiruan memiliki puncak 12.0 menit jauh lebih tinggi dan penanda 16.0 menit yang tidak ada di Asli.
    """
    files: Dict[str, Path] = {}
    rng = np.random.default_rng(seed)
    for cls, marker in (("Asli", 0.0), ("Tiruan", 1.0)):
        folder = root / cls
        folder.mkdir(parents=True, exist_ok=True)
        for series, series_scale in (("Melati", 1.0), ("Mawar", 0.6)):
            for replicate in (1, 2, 3):
                scale = {6.0: series_scale, 9.5: series_scale, 12.0: 1.0 + 6.0 * marker}
                extra = [(16.0, 8.0e5, 0.025)] if marker else []
                noise_scale = {rt: float(rng.normal(1.0, 0.05)) for rt, _, _ in COMMON_PEAKS}
                for rt in scale:
                    scale[rt] *= noise_scale[rt]
                rt, y = make_trace(synthetic_peaks(scale, extra), jitter=float(rng.normal(0, 0.004)),
                                   seed=int(rng.integers(1_000_000)))
                name = f"{series} {replicate}"
                files[f"{cls}/{name}"] = write_two_column_csv(folder / f"{name}.csv", rt, y)
    return files
