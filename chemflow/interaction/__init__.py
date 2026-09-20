"""
Ekspor otomatis interaksi ligan-reseptor dari BIOVIA Discovery Studio.

Menggantikan langkah manual pada analisis similaritas: diagram 2D dan tabel
Non-bond tiap kompleks diambil lewat GUI BIOVIA, dengan mouse dan keyboard
dikunci selama ekspor. Hanya Windows dengan BIOVIA Discovery Studio
(Visualizer gratis cukup) yang bisa menjalankannya; modul ini aman diimpor
di platform lain.
"""

from chemflow.interaction.biovia_install import (
    BioviaInstallation, BioviaLocator, BioviaUnavailableError, automation_dependencies_ok, detect_biovia,
)
from chemflow.interaction.exporter import (
    ExportSummary, InteractionBackend, InteractionExporter, InteractionJob, discover_jobs, export_interactions,
)
from chemflow.interaction.input_lock import InputLock, InputLockAborted
from chemflow.interaction.table import NonbondTable, write_interaction_xlsx

__all__ = [
    "BioviaInstallation",
    "BioviaLocator",
    "BioviaUnavailableError",
    "automation_dependencies_ok",
    "detect_biovia",
    "ExportSummary",
    "InteractionBackend",
    "InteractionExporter",
    "InteractionJob",
    "InputLock",
    "InputLockAborted",
    "NonbondTable",
    "discover_jobs",
    "export_interactions",
    "write_interaction_xlsx",
]
