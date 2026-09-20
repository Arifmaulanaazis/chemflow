"""
Analisis similaritas interaksi satu langkah: hitung, tulis Excel, dan buat grafik.

Dipakai bersama oleh ``chemflow similarity`` dan tahap similaritas otomatis pada ``chemflow run``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from chemflow.similarity.similarity import SimilarityAnalyzer, SimilarityResult, export_similarity_results


@dataclass
class SimilarityReport:
    """Hasil analisis: pasangan yang berhasil dihitung, berkas Excel, dan grafik yang dibuat."""
    results: List[SimilarityResult]
    workbook: Optional[Path] = None
    plots: List[Path] = field(default_factory=list)


def run_similarity_report(
    output_dir: "str | Path",
    interactions_dir: Optional["str | Path"] = None,
    interaction_suffix: str = "_interaksi.xlsx",
    result_filename: str = "similaritas_interaksi.xlsx",
    make_plots: bool = True,
    dpi: int = 300,
    formats: Sequence[str] = ("png",),
    max_rows: int = 30,
    max_cols: int = 20,
    logger: Optional[logging.Logger] = None,
) -> SimilarityReport:
    """Hitung similaritas seluruh kompleks di ``<output_dir>/complexes/`` dan tulis laporannya.

    Excel ditulis ke ``<output_dir>/<result_filename>`` dan grafik ke ``<output_dir>/analytics/``.
    Bila tidak ada pasangan yang bisa dihitung, tidak ada berkas yang ditulis.

    Raises:
        FileNotFoundError: ``complexes/`` tidak ada (belum pernah ``chemflow run``).
    """
    output_dir = Path(output_dir)
    results = SimilarityAnalyzer(logger).analyze_output_dir(
        output_dir, interactions_dir=interactions_dir, interaction_suffix=interaction_suffix,
    )
    if not results:
        return SimilarityReport(results=[])

    workbook = export_similarity_results(results, output_dir / result_filename, logger)
    report = SimilarityReport(results=results, workbook=workbook)
    if make_plots:
        from chemflow.analytics.style import normalize_formats
        from chemflow.similarity.plots import SimilarityPlotter

        plotter = SimilarityPlotter(output_dir / "analytics", dpi=dpi, formats=normalize_formats(formats),
                                    max_rows=max_rows, max_cols=max_cols)
        report.plots = plotter.plot_all(results)
    return report
