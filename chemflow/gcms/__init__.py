"""
Analisis GC-MS opsional: pembacaan lintas format, pemrosesan kromatogram, kemometrik
(PCA, HCA, PLS-DA, LDA, uji univariat), pencocokan pustaka, dan skrining alergen.

Berdiri sendiri dan tidak diperlukan oleh pipeline docking. Lihat ``docs/gcms-analysis.md``.
"""

from chemflow.gcms.analysis import (
    GCMS_DIRNAME, GcmsAnalyzer, GcmsConfig, GcmsResult, assign_metadata, load_saved_config, read_groups_table,
    run_gcms_analysis,
)
from chemflow.gcms.library import (
    EU_ALLERGENS, Compound, kovats_index, load_alkanes, load_library, match_by_name, match_by_retention,
)
from chemflow.gcms.models import Chromatogram, FeatureTable, Peak, infer_class, infer_series
from chemflow.gcms.readers import (
    SUPPORTED_EXTENSIONS, GcmsDataset, GcmsFormatError, collect_files, normalize_rt, read_data, read_file,
)

__all__ = [
    "Chromatogram",
    "Compound",
    "EU_ALLERGENS",
    "FeatureTable",
    "GCMS_DIRNAME",
    "GcmsAnalyzer",
    "GcmsConfig",
    "GcmsDataset",
    "GcmsFormatError",
    "GcmsResult",
    "Peak",
    "SUPPORTED_EXTENSIONS",
    "assign_metadata",
    "collect_files",
    "infer_class",
    "infer_series",
    "kovats_index",
    "load_alkanes",
    "load_library",
    "load_saved_config",
    "match_by_name",
    "match_by_retention",
    "normalize_rt",
    "read_data",
    "read_file",
    "read_groups_table",
    "run_gcms_analysis",
]
