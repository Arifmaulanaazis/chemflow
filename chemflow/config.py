"""
Konfigurasi pipeline chemflow.

Satu dataclass datar (`PipelineConfig`) menampung seluruh parameter yang
bisa diatur pengguna, dikelompokkan lewat komentar section. Konvensi:
``Optional[X] = None`` berarti "belum diset -> auto-detect/fallback di
tahap berikutnya" (mis. ``size_x=None`` memicu auto-sizing gridbox
berbasis ekstensi ligan).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from chemflow.analytics.style import FIG_DPI, normalize_formats

_PATH_FIELDS = ("ligand_excel", "receptor_excel", "output_dir", "vina_executable", "openbabel_path", "admet_file", "biovia_exe",
                "gcms_groups", "gcms_library")
_PATH_LIST_FIELDS = ("gcms_data",)


@dataclass
class PipelineConfig:
    """Parameter lengkap satu eksekusi pipeline chemflow.

    Semua path disimpan sebagai ``Path`` yang sudah di-resolve di
    ``__post_init__`` supaya modul-modul lain tak perlu memikirkan
    relative-path lagi.
    """

    # Input
    ligand_excel: Path
    receptor_excel: Path
    output_dir: Path = Path("chemflow_output")

    # Pemetaan kolom Excel ligan (override manual, None = auto-detect)
    ligand_name_col: Optional[str] = None
    ligand_smiles_col: Optional[str] = None
    ligand_group_col: Optional[str] = None

    # Pemetaan kolom Excel reseptor (override manual)
    receptor_pdb_col: Optional[str] = None
    receptor_cx_col: Optional[str] = None
    receptor_cy_col: Optional[str] = None
    receptor_cz_col: Optional[str] = None
    receptor_sx_col: Optional[str] = None
    receptor_sy_col: Optional[str] = None
    receptor_sz_col: Optional[str] = None

    # Gridbox
    default_box_size: float = 20.0          # Angstrom, cadangan bila tak ada ligan native untuk menurunkan ukuran
    box_padding: float = 8.0                # padding di atas ekstensi ligan native saat ukuran diturunkan otomatis
    interactive_gridbox: bool = True        # boleh prompt TTY memilih ligan native

    # Preparasi ligan
    force_field: str = "MMFF94"             # "MMFF94" | "UFF" (fallback otomatis jika MMFF gagal)
    minimize_max_iters: int = 1000
    generate_2d_image: bool = True

    # Preparasi reseptor
    remove_waters: bool = True
    remove_hetero_ligands: bool = True
    keep_metals: bool = True
    kollman_fallback_zero: bool = True      # True = atom di luar tabel diberi charge 0.0 (ter-log)

    # Docking (AutoDock Vina)
    vina_version: Optional[str] = None      # None = pilih versi terbaru yang kompatibel
    vina_executable: Optional[Path] = None  # override manual, skip auto-download/PATH lookup
    exhaustiveness: int = 8
    num_modes: int = 9
    energy_range: float = 3.0
    seed: Optional[int] = None              # None = seed acak per replikat
    n_replicates: int = 1

    # Merge kompleks reseptor-ligan
    merge_mode: str = "best"                # "best" = 1 pose terbaik lintas replikat, "all" = semua pose semua replikat

    # Ligan native (kokristal): di-redock dan ikut semua analitik sebagai grup "Native"
    include_native: bool = True
    native_match_radius: float = 8.0        # Angstrom, jarak maks pusat gridbox Excel ke pusat native agar dianggap situs yang sama

    # Validasi RMSD redocking
    run_rmsd_validation: bool = False
    rmsd_threshold_good: float = 2.0        # Angstrom, Hevener et al. 2009 (PMC2788795)
    rmsd_threshold_acceptable: float = 3.0

    # OpenBabel
    openbabel_path: Optional[Path] = None   # override manual; default: cari "obabel" di PATH

    # ADMET
    run_admet: bool = True
    admet_file: Optional[Path] = None       # CSV/Excel hasil unduhan ADMETLab3; jika diisi, scraping dilewati
    admet_batch_size: int = 50
    admet_ssl_verify: bool = False          # ADMETLab3 kadang pakai sertifikat SSL bermasalah

    # PubChem
    fetch_missing_smiles: bool = True
    interactive_pubchem_fallback: bool = True  # tanya SMILES manual/skip jika PubChem gagal (butuh TTY)

    # Analitik
    generate_charts: bool = True
    run_pca: bool = True             # menghasilkan plot 2D & 3D sekaligus (3D dilewati jika data tak cukup)
    run_hca: bool = True             # dendrogram hierarchical cluster analysis
    run_heatmap: bool = True         # heatmap afinitas (reseptor x ligan) & properti (ligan x parameter)
    figure_dpi: int = FIG_DPI        # resolusi raster seluruh grafik
    figure_formats: Tuple[str, ...] = ("png",)  # format tambahan: "svg", "pdf" (PNG selalu ditulis)
    plot_max_rows: int = 30          # baris/bar/ligan maksimum per gambar, lebihnya dipotong jadi bagian; 0 = tidak dipotong
    plot_max_cols: int = 20          # kolom maksimum per gambar heatmap; 0 = tidak dipotong

    # Interaksi BIOVIA dan similaritas (Windows dengan BIOVIA Discovery Studio; Visualizer gratis cukup)
    run_similarity: Optional[bool] = None   # None = otomatis bila Windows dan BIOVIA terdeteksi; True = paksa; False = matikan
    biovia_exe: Optional[Path] = None       # override manual; default: deteksi otomatis instalasi terbaru
    biovia_launch_timeout: float = 90.0     # detik menunggu jendela BIOVIA muncul
    lock_input: bool = True                 # kunci mouse dan keyboard selama ekspor BIOVIA

    # Analisis GC-MS opsional (berdiri sendiri, tidak memengaruhi docking; opsi lain lewat 'chemflow gcms')
    gcms_data: Tuple[Path, ...] = ()        # berkas, folder, atau pola data GC-MS; kosong = tidak dijalankan
    gcms_groups: Optional[Path] = None      # tabel sampel, seri, kelas
    gcms_library: Optional[Path] = None     # pustaka senyawa (nama, RT atau RI, CAS, SMILES)

    # Logging
    verbose: bool = False
    log_level: str = "INFO"
    show_progress: bool = True       # progress bar (tqdm) di terminal, di samping log biasa

    def __post_init__(self) -> None:
        self.ligand_excel = Path(self.ligand_excel).resolve()
        self.receptor_excel = Path(self.receptor_excel).resolve()
        self.output_dir = Path(self.output_dir).resolve()
        if self.vina_executable is not None:
            self.vina_executable = Path(self.vina_executable).resolve()
        if self.openbabel_path is not None:
            self.openbabel_path = Path(self.openbabel_path).resolve()
        if self.biovia_exe is not None:
            self.biovia_exe = Path(self.biovia_exe).resolve()
        if self.admet_file is not None:
            self.admet_file = Path(self.admet_file).resolve()
            if not self.run_admet:
                raise ValueError("admet_file tidak bisa dipakai bersamaan dengan run_admet=False.")
            if not self.admet_file.exists():
                raise FileNotFoundError(f"File ADMET tidak ditemukan: {self.admet_file}")
        self.gcms_data = tuple(Path(p) for p in ([self.gcms_data] if isinstance(self.gcms_data, (str, Path)) else self.gcms_data))
        for name in ("gcms_groups", "gcms_library"):
            if getattr(self, name) is not None:
                setattr(self, name, Path(getattr(self, name)).resolve())
        for path in self.gcms_data:
            if not any(ch in str(path) for ch in "*?[") and not path.exists():
                raise FileNotFoundError(f"Data GC-MS tidak ditemukan: {path}")
        if self.biovia_launch_timeout <= 0:
            raise ValueError(f"biovia_launch_timeout harus > 0, dapat: {self.biovia_launch_timeout}")
        if self.run_similarity is True and not (self.include_native or self.run_rmsd_validation):
            raise ValueError("run_similarity membutuhkan ligan native sebagai referensi; jangan pakai include_native=False.")
        if self.figure_dpi < 72:
            raise ValueError(f"figure_dpi harus >= 72, dapat: {self.figure_dpi}")
        if self.plot_max_rows < 0 or self.plot_max_cols < 0:
            raise ValueError(
                f"plot_max_rows dan plot_max_cols harus >= 0 (0 = tidak dipotong), "
                f"dapat: {self.plot_max_rows}, {self.plot_max_cols}"
            )
        self.figure_formats = normalize_formats(self.figure_formats)

        if self.force_field not in ("MMFF94", "UFF"):
            raise ValueError(f"force_field harus 'MMFF94' atau 'UFF', dapat: {self.force_field!r}")
        if self.n_replicates < 1:
            raise ValueError(f"n_replicates harus >= 1, dapat: {self.n_replicates}")
        if self.exhaustiveness < 1:
            raise ValueError(f"exhaustiveness harus >= 1, dapat: {self.exhaustiveness}")
        if self.merge_mode not in ("best", "all"):
            raise ValueError(f"merge_mode harus 'best' atau 'all', dapat: {self.merge_mode!r}")
        if not self.ligand_excel.exists():
            raise FileNotFoundError(f"File Excel ligan tidak ditemukan: {self.ligand_excel}")
        if not self.receptor_excel.exists():
            raise FileNotFoundError(f"File Excel reseptor tidak ditemukan: {self.receptor_excel}")

    def to_dict(self) -> Dict[str, Any]:
        """Seluruh parameter sebagai dict JSON-aman (Path menjadi str, tuple menjadi list)."""
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
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        """Bangun ulang dari ``to_dict()``; kunci tak dikenal diabaikan agar state versi lain tetap terbaca."""
        known = {item.name for item in fields(cls)}
        kwargs = {key: value for key, value in data.items() if key in known}
        for name in _PATH_FIELDS:
            if kwargs.get(name) is not None:
                kwargs[name] = Path(kwargs[name])
        if "figure_formats" in kwargs:
            kwargs["figure_formats"] = tuple(kwargs["figure_formats"])
        for name in _PATH_LIST_FIELDS:
            if name in kwargs:
                paths = [Path(v) for v in kwargs[name]]
                missing = [p for p in paths if not any(ch in str(p) for ch in "*?[") and not p.exists()]
                if missing:
                    logging.getLogger("chemflow").warning(
                        f"Data GC-MS tidak ditemukan lagi, dilewati saat resume: {', '.join(map(str, missing))}")
                kwargs[name] = tuple(p for p in paths if p not in missing)
        return cls(**kwargs)

    @property
    def ligand_dir(self) -> Path:
        return self.output_dir / "ligands"

    @property
    def receptor_dir(self) -> Path:
        return self.output_dir / "receptors"

    @property
    def docking_dir(self) -> Path:
        return self.output_dir / "docking"

    @property
    def complex_dir(self) -> Path:
        return self.output_dir / "complexes"

    @property
    def analytics_dir(self) -> Path:
        return self.output_dir / "analytics"

    @property
    def interactions_dir(self) -> Path:
        return self.output_dir / "interaksi"

    @property
    def cache_dir(self) -> Path:
        return self.output_dir / "_cache"
