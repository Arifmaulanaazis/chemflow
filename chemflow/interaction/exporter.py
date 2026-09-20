"""
Ekspor otomatis interaksi ligan-reseptor untuk seluruh kompleks hasil ``chemflow run``.

Setiap ``<output>/complexes/<kunci>/<basis>.pdb`` dibuka di BIOVIA, lalu
diagram 2D dan tabel Non-bond disimpan sebagai
``<interaksi>/<kunci>/<basis>_interaksi.png`` dan ``.xlsx``. Nama dan struktur
folder itu persis yang dicari ``SimilarityAnalyzer``, jadi hasilnya langsung
bisa dipakai analisis similaritas. Kompleks yang hasilnya sudah lengkap
dilewati sehingga ekspor bisa dilanjutkan setelah terhenti.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional, Protocol, Tuple

from chemflow.interaction.input_lock import InputLock
from chemflow.interaction.table import NonbondTable, write_interaction_xlsx

XLSX_SUFFIX = "_interaksi.xlsx"


class InteractionBackend(Protocol):
    """Operasi BIOVIA yang dibutuhkan pengekspor (dipisah agar bisa diuji tanpa aplikasinya)."""

    def prepare(self) -> None: ...
    def is_alive(self) -> bool: ...
    def recover(self) -> None: ...
    def close(self) -> None: ...
    def open_complex(self, path: Path, ligand_chain: Optional[str], ligand_resname: Optional[str]) -> str: ...
    def export_diagram(self, path: Path) -> None: ...
    def read_nonbond(self) -> NonbondTable: ...
    def close_complex(self, stem: str) -> None: ...


@dataclass(frozen=True)
class InteractionJob:
    """Satu kompleks yang akan diekspor beserta identitas ligannya dari sidecar JSON."""
    receptor_key: str
    pdb_path: Path
    output_dir: Path
    xlsx_suffix: str = XLSX_SUFFIX
    ligand_chain: Optional[str] = None
    ligand_resname: Optional[str] = None
    is_native: bool = False

    @property
    def stem(self) -> str:
        return self.pdb_path.stem

    @property
    def xlsx_path(self) -> Path:
        return self.output_dir / f"{self.stem}{self.xlsx_suffix}"

    @property
    def png_path(self) -> Path:
        return self.xlsx_path.with_suffix(".png")

    @property
    def is_complete(self) -> bool:
        return all(p.is_file() and p.stat().st_size > 0 for p in (self.xlsx_path, self.png_path))


@dataclass
class ExportSummary:
    """Hasil satu ekspor: pekerjaan berhasil, gagal (dengan pesan), dan yang dilewati karena sudah lengkap."""
    succeeded: List[InteractionJob] = field(default_factory=list)
    failed: List[Tuple[InteractionJob, str]] = field(default_factory=list)
    skipped: int = 0


def _read_sidecar(pdb_path: Path) -> dict:
    try:
        return json.loads(pdb_path.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def discover_jobs(output_dir: "str | Path", interactions_dir: Optional["str | Path"] = None,
                  xlsx_suffix: str = XLSX_SUFFIX, receptor: Optional[str] = None,
                  force: bool = False, logger: Optional[logging.Logger] = None) -> Tuple[List[InteractionJob], int]:
    """Susun antrean dari ``<output>/complexes/`` dan hitung berapa yang sudah lengkap.

    Ligan native diproses lebih dulu di tiap reseptor karena similaritas
    membutuhkannya sebagai acuan.

    Returns:
        (pekerjaan yang perlu dijalankan, jumlah yang dilewati karena sudah lengkap).

    Raises:
        FileNotFoundError: folder ``complexes/`` tidak ada.
    """
    log = logger or logging.getLogger(__name__)
    output_dir = Path(output_dir)
    complex_dir = output_dir / "complexes"
    if not complex_dir.is_dir():
        raise FileNotFoundError(
            f"Folder kompleks tidak ditemukan: {complex_dir}. Jalankan 'chemflow run' dulu."
        )
    root = Path(interactions_dir) if interactions_dir else output_dir / "interaksi"

    jobs: List[InteractionJob] = []
    skipped = 0
    for receptor_dir in sorted(p for p in complex_dir.iterdir() if p.is_dir()):
        if receptor and receptor_dir.name != receptor:
            continue
        batch = []
        for pdb_path in receptor_dir.glob("*_complex.pdb"):
            meta = _read_sidecar(pdb_path)
            if not meta:
                log.warning(f"Sidecar JSON tidak ada untuk '{pdb_path.name}': ligan dipilih sebagai ligan terakhir BIOVIA.")
            batch.append(InteractionJob(
                receptor_key=receptor_dir.name, pdb_path=pdb_path, output_dir=root / receptor_dir.name,
                xlsx_suffix=xlsx_suffix, ligand_chain=meta.get("ligand_chain") or None,
                ligand_resname=meta.get("ligand_resname") or None, is_native=bool(meta.get("is_native")),
            ))
        for job in sorted(batch, key=lambda j: (not j.is_native, j.pdb_path.name)):
            if job.is_complete and not force:
                skipped += 1
            else:
                jobs.append(job)
    return jobs, skipped


class InteractionExporter:
    """Jalankan antrean secara berurutan: GUI BIOVIA memakai satu fokus mouse dan keyboard."""

    def __init__(self, backend: InteractionBackend, logger: Optional[logging.Logger] = None,
                 show_progress: bool = True, input_lock: Optional[InputLock] = None) -> None:
        self._backend = backend
        self._log = logger or logging.getLogger(__name__)
        self._show_progress = show_progress
        self._lock = input_lock or InputLock(enabled=False)

    def run(self, jobs: List[InteractionJob]) -> ExportSummary:
        """Ekspor semua ``jobs``. Kegagalan satu kompleks dicatat dan tidak menghentikan yang lain."""
        from tqdm import tqdm

        summary = ExportSummary()
        if not jobs:
            return summary
        with self._lock:
            self._backend.prepare()
            try:
                for job in tqdm(jobs, desc="Ekspor interaksi BIOVIA", unit="kompleks", disable=not self._show_progress):
                    self._lock.pulse()
                    label = f"{job.receptor_key}/{job.stem}"
                    try:
                        if not self._backend.is_alive():
                            self._log.warning("Proses BIOVIA terputus; menghubungkan ulang.")
                            self._backend.prepare()
                        count = self._export_one(job)
                    except Exception as exc:
                        summary.failed.append((job, str(exc)))
                        self._log.error(f"Ekspor interaksi gagal untuk {label}: {exc}")
                        self._log.debug("Detail error:", exc_info=True)
                        try:
                            if self._backend.is_alive():
                                self._backend.recover()
                        except Exception:
                            self._log.debug("Pemulihan antarmuka belum berhasil.", exc_info=True)
                    else:
                        summary.succeeded.append(job)
                        self._log.info(f"Interaksi {label}: {count} baris")
            finally:
                self._backend.close()
        return summary

    def _export_one(self, job: InteractionJob) -> int:
        """Ekspor satu kompleks; hasil dipindahkan dari folder sementara hanya bila keduanya utuh."""
        job.output_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".biovia-", dir=job.output_dir) as temporary:
            png_path = Path(temporary) / job.png_path.name
            xlsx_path = Path(temporary) / job.xlsx_path.name
            self._backend.open_complex(job.pdb_path, job.ligand_chain, job.ligand_resname)
            try:
                self._backend.export_diagram(png_path)
                count = write_interaction_xlsx(self._backend.read_nonbond(), xlsx_path)
            finally:
                try:
                    self._backend.close_complex(job.stem)
                except Exception as exc:
                    self._log.warning(f"Kompleks '{job.stem}' belum tertutup di BIOVIA: {exc}")
            for path in (png_path, xlsx_path):
                if not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError(f"Hasil ekspor tidak terbentuk atau kosong: {path.name}")
            png_path.replace(job.png_path)
            xlsx_path.replace(job.xlsx_path)
        return count


def export_interactions(output_dir: "str | Path", interactions_dir: Optional["str | Path"] = None, *,
                        executable: Optional[Path] = None, launch_timeout: float = 90.0,
                        xlsx_suffix: str = XLSX_SUFFIX, receptor: Optional[str] = None, force: bool = False,
                        show_progress: bool = True, backend: Optional[InteractionBackend] = None,
                        lock_input: Optional[bool] = None, logger: Optional[logging.Logger] = None) -> ExportSummary:
    """Ekspor interaksi seluruh kompleks di ``<output_dir>/complexes/`` lewat BIOVIA.

    Args:
        output_dir: folder output ``chemflow run``.
        interactions_dir: folder hasil (default ``<output_dir>/interaksi``).
        executable: jalur DiscoveryStudio<tahun>.exe; ``None`` = deteksi otomatis, tahun terbaru.
        launch_timeout: batas menunggu jendela BIOVIA muncul, dalam detik.
        xlsx_suffix: akhiran nama berkas Excel (harus sama dengan ``--interaction-suffix`` similaritas).
        receptor: hanya folder reseptor ini.
        force: ekspor ulang walau hasilnya sudah lengkap.
        backend: pengganti ``BioviaClient`` (untuk pengujian).
        lock_input: kunci mouse dan keyboard selama ekspor. ``None`` (bawaan) = dikunci hanya bila
            ``BioviaClient`` asli dipakai; tekan Esc tiga kali untuk membatalkan.

    Raises:
        FileNotFoundError: ``complexes/`` tidak ada.
        BioviaUnavailableError: bukan Windows, dependensi kurang, atau BIOVIA tidak ditemukan.
        BioviaLicenseError: BIOVIA menolak lisensi.
    """
    log = logger or logging.getLogger(__name__)
    jobs, skipped = discover_jobs(output_dir, interactions_dir, xlsx_suffix, receptor, force, log)
    if not jobs:
        log.info(f"Interaksi BIOVIA: {skipped} kompleks sudah lengkap, tidak ada yang perlu diekspor.")
        return ExportSummary(skipped=skipped)
    log.info(f"Interaksi BIOVIA: {len(jobs)} kompleks akan diekspor, {skipped} dilewati (sudah lengkap). "
             f"Jangan memakai mouse atau keyboard sampai selesai.")
    lock = InputLock(enabled=True if lock_input is None and backend is None else bool(lock_input), logger=log)
    if backend is None:
        from chemflow.interaction.biovia_gui import BioviaClient

        backend = BioviaClient(executable, launch_timeout, logger=log, input_lock=lock)
    summary = InteractionExporter(backend, log, show_progress, input_lock=lock).run(jobs)
    summary.skipped = skipped
    return summary
