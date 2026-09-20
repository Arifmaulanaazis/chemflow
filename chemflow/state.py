"""
Status run yang tahan crash untuk ``chemflow resume``.

Semua checkpoint ditulis atomik (tulis ke file sementara, lalu ``os.replace``)
sehingga terminal ditutup, Ctrl+C, atau komputer mati tidak pernah
meninggalkan JSON setengah jadi. Path di dalam checkpoint disimpan relatif
terhadap folder output, jadi folder boleh dipindah atau diganti namanya.

Isi ``<output>/_state/``:
    config.json    seluruh ``PipelineConfig`` + peta salinan input
    inputs/        salinan Excel ligan, reseptor, dan file ADMET
    progress.json  tahap terakhir dan flag ``finished``
    ligands.json   ligan hasil baca Excel + resolusi PubChem
    admet_cache.json  hasil ADMET per SMILES yang sudah dikirim

Checkpoint per item (ligan, reseptor, run docking) berada di samping artefaknya
(``prepared.json``, ``repNN.json``), lihat ``pipeline.py`` dan ``docking_matrix.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

STATE_DIRNAME = "_state"
SCHEMA_VERSION = 1

_INPUT_FIELDS = {
    "ligand_excel": "ligands",
    "receptor_excel": "receptors",
    "admet_file": "admet",
}


def write_json_atomic(path: "str | Path", data: Any) -> None:
    """Tulis JSON secara atomik: file tujuan selalu utuh (versi lama atau baru), tak pernah separuh."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Windows: pemindai antivirus/indeks kadang menahan file sesaat.
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def read_json(path: "str | Path", default: Any = None) -> Any:
    """Baca JSON; ``default`` bila file tak ada atau rusak."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def to_rel(path: Optional["str | Path"], base: "str | Path") -> Optional[str]:
    """Path relatif POSIX terhadap ``base``; path di luar ``base`` disimpan absolut."""
    if path is None:
        return None
    path = Path(path)
    try:
        return path.resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return str(path)


def from_rel(text: Optional[str], base: "str | Path") -> Optional[Path]:
    """Kebalikan ``to_rel``: path relatif dihitung dari ``base``, path absolut dipakai apa adanya."""
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else Path(base) / path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunState:
    """Pengelola ``<output>/_state/``: config, salinan input, dan progres run."""

    def __init__(self, output_dir: "str | Path") -> None:
        self.output_dir = Path(output_dir).resolve()
        self.dir = self.output_dir / STATE_DIRNAME

    @property
    def config_path(self) -> Path:
        return self.dir / "config.json"

    @property
    def progress_path(self) -> Path:
        return self.dir / "progress.json"

    @property
    def inputs_dir(self) -> Path:
        return self.dir / "inputs"

    @property
    def ligands_path(self) -> Path:
        return self.dir / "ligands.json"

    @property
    def admet_cache_path(self) -> Path:
        return self.dir / "admet_cache.json"

    def exists(self) -> bool:
        return self.config_path.exists()

    def is_unfinished(self) -> bool:
        """True bila ada state tetapi run terakhir belum selesai (kandidat ``resume``)."""
        if not self.exists():
            return False
        progress = read_json(self.progress_path, {})
        return not progress.get("finished", False)

    def save_config(self, config: Any) -> None:
        """Simpan konfigurasi dan salin file input.

        Saat dipanggil untuk run yang di-resume, path input sudah menunjuk ke
        salinan di ``inputs/``: salinan dibiarkan dan path asli dipertahankan.
        """
        previous = read_json(self.config_path, {}) or {}
        previous_original = previous.get("config", {})
        data = config.to_dict()
        inputs: Dict[str, str] = dict(previous.get("inputs", {}))

        for field, stem in _INPUT_FIELDS.items():
            source = getattr(config, field, None)
            if source is None:
                continue
            source = Path(source)
            if self.inputs_dir in source.resolve().parents:
                if field in previous_original:
                    data[field] = previous_original[field]
                continue
            target = self.inputs_dir / f"{stem}{source.suffix}"
            try:
                self.inputs_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                inputs[field] = target.relative_to(self.dir).as_posix()
            except OSError:
                inputs.pop(field, None)

        write_json_atomic(self.config_path, {
            "schema": SCHEMA_VERSION, "chemflow_version": _version(),
            "config": data, "inputs": inputs,
        })

    def load_config(self):
        """Bangun ``PipelineConfig`` dari state; input memakai salinan, output = folder ini.

        Raises:
            FileNotFoundError: folder belum punya state (run dibuat sebelum fitur resume).
            ValueError: skema state tidak dikenal.
        """
        from chemflow.config import PipelineConfig

        payload = read_json(self.config_path)
        if payload is None:
            raise FileNotFoundError(
                f"Tidak ada state resume di '{self.output_dir}' ({STATE_DIRNAME}/config.json tidak ditemukan). "
                f"Folder ini belum pernah dijalankan dengan 'chemflow run', atau dibuat sebelum fitur resume ada. "
                f"Jalankan ulang dengan 'chemflow run'."
            )
        if payload.get("schema") != SCHEMA_VERSION:
            raise ValueError(
                f"Skema state resume ({payload.get('schema')!r}) tidak cocok dengan versi chemflow ini "
                f"({SCHEMA_VERSION}). Jalankan ulang dengan 'chemflow run'."
            )

        data = dict(payload["config"])
        for field, relative in payload.get("inputs", {}).items():
            snapshot = self.dir / relative
            if snapshot.exists():
                data[field] = str(snapshot)
        data["output_dir"] = str(self.output_dir)
        return PipelineConfig.from_dict(data)

    def update_progress(self, stage: str, finished: bool = False) -> None:
        current = read_json(self.progress_path, {}) or {}
        current.setdefault("started_at", _now())
        current.update({"schema": SCHEMA_VERSION, "stage": stage, "finished": finished, "updated_at": _now()})
        write_json_atomic(self.progress_path, current)

    def read_progress(self) -> Dict[str, Any]:
        return read_json(self.progress_path, {}) or {}

    def clear_checkpoints(self) -> None:
        """Hapus checkpoint run lama: run baru mengerjakan semuanya dari awal.

        Hanya berkas checkpoint yang dihapus (bukan hasil docking, ligan, atau reseptor), supaya
        checkpoint lama tidak pernah tercampur dengan run baru yang konfigurasinya bisa berbeda.
        """
        for path in (self.ligands_path, self.admet_cache_path, self.progress_path):
            try:
                path.unlink()
            except OSError:
                pass
        for pattern in ("ligands/*/prepared.json", "receptors/*/prepared.json", "docking/*/*/rep*.json"):
            for path in self.output_dir.glob(pattern):
                try:
                    path.unlink()
                except OSError:
                    pass


def _version() -> str:
    try:
        from chemflow import __version__
        return __version__
    except Exception:
        return "unknown"
