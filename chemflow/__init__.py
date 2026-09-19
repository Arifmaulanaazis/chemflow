"""
chemflow: pipeline untuk preparasi ligan/reseptor, prediksi ADMET &
sifat fisikokimia, docking AutoDock Vina, penggabungan kompleks, dan
analisis kemometrik (PCA, HCA, heatmap) berbasis Excel.

Dipakai sebagai CLI (``python -m chemflow``) atau diimpor sebagai library:

    from chemflow import PipelineConfig, Pipeline

    config = PipelineConfig(ligand_excel="ligan.xlsx", receptor_excel="reseptor.xlsx")
    Pipeline(config).run()

Komponen individual (preparasi ligan, docking, analitik, dst) juga bisa
dipakai langsung tanpa lewat Excel/CLI. Lihat ``docs/library-usage.md``
untuk contoh lengkap tiap komponen.
"""

from __future__ import annotations

from chemflow.admet.admet_file import load_admet_rows, read_admet_table
from chemflow.admet.admet_rules import classify_admet_value
from chemflow.admet.admetlab_scraper import AdmetLabScraper
from chemflow.analytics.charts import ChartBuilder
from chemflow.analytics.hca import HcaResult, HierarchicalClustering
from chemflow.analytics.heatmap import HeatmapBuilder
from chemflow.analytics.pca import ChemometricPCA, PcaResult
from chemflow.chem.descriptors import ExtendedDescriptors, LipinskiCalculator, LipinskiResult
from chemflow.chem.ligand_preparer import LigandPreparer, LigandPrepResult
from chemflow.chem.mol_converter import OpenBabelConverter
from chemflow.chem.pubchem_client import PubChemResolver, prompt_manual_smiles
from chemflow.chem.receptor_preparer import ReceptorPreparer
from chemflow.config import PipelineConfig
from chemflow.docking.docking_matrix import (
    DockingOrchestrator, DockingRunResult, ReceptorDockingTarget, compute_replicate_stats,
)
from chemflow.docking.grid_box import GridBox
from chemflow.docking.merge import merge_complex
from chemflow.docking.rmsd_validation import RedockingValidator, RmsdValidationResult
from chemflow.docking.vina_manager import VinaReleaseManager
from chemflow.docking.vina_runner import VinaRunner, resolve_vina_executable
from chemflow.io.excel_ligands import LigandRecord, read_ligands
from chemflow.io.excel_receptors import ReceptorEntry, read_receptors
from chemflow.io.pdb_fetcher import FetchedReceptor, NativeLigand, fetch_pdb
from chemflow.io.receptor_config import ReceptorConfigRow, suggest_box_size, write_receptor_config
from chemflow.io.result_exporter import export_results
from chemflow.pipeline import Pipeline
from chemflow.similarity.biovia_reader import (
    AtomSpec, BiovaInteraction, ProteinLigandContact, filter_protein_ligand,
    parse_atom_spec, read_biovia_interactions,
)
from chemflow.similarity.plots import SimilarityPlotter
from chemflow.similarity.similarity import (
    SimilarityAnalyzer, SimilarityResult, compute_similarity, export_similarity_results,
)

__version__ = "0.1.0"

__all__ = [
    "Pipeline",
    "PipelineConfig",
    "LigandPreparer",
    "LigandPrepResult",
    "ReceptorPreparer",
    "OpenBabelConverter",
    "PubChemResolver",
    "prompt_manual_smiles",
    "LipinskiCalculator",
    "LipinskiResult",
    "ExtendedDescriptors",
    "AdmetLabScraper",
    "load_admet_rows",
    "read_admet_table",
    "classify_admet_value",
    "GridBox",
    "VinaReleaseManager",
    "VinaRunner",
    "resolve_vina_executable",
    "DockingOrchestrator",
    "ReceptorDockingTarget",
    "DockingRunResult",
    "compute_replicate_stats",
    "RedockingValidator",
    "RmsdValidationResult",
    "merge_complex",
    "read_ligands",
    "LigandRecord",
    "read_receptors",
    "ReceptorEntry",
    "fetch_pdb",
    "FetchedReceptor",
    "NativeLigand",
    "ReceptorConfigRow",
    "suggest_box_size",
    "write_receptor_config",
    "export_results",
    "ChartBuilder",
    "ChemometricPCA",
    "PcaResult",
    "HierarchicalClustering",
    "HcaResult",
    "HeatmapBuilder",
    "read_biovia_interactions",
    "parse_atom_spec",
    "filter_protein_ligand",
    "AtomSpec",
    "BiovaInteraction",
    "ProteinLigandContact",
    "compute_similarity",
    "SimilarityAnalyzer",
    "SimilarityResult",
    "SimilarityPlotter",
    "export_similarity_results",
]
