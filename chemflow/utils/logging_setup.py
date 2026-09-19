"""
Konfigurasi logging terpusat untuk chemflow.

Semua modul memakai logger bernama ``chemflow.<submodule>`` agar mudah
difilter. Output ganda: konsol (ringkas) + file log per-run (lengkap,
di dalam direktori output run tsb) supaya setiap langkah pipeline punya
jejak audit yang bisa diperiksa ulang.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

_CONSOLE_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s"
_FILE_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s:%(lineno)d: %(message)s"
_DATE_FORMAT = "%H:%M:%S"


def setup_logging(
    log_file: Optional[Path] = None,
    level: int = logging.INFO,
    logger_name: str = "chemflow",
) -> logging.Logger:
    """Siapkan root logger chemflow dengan handler konsol (+file opsional).

    Args:
        log_file: path file log. Jika diberikan, direktori induknya dibuat
            otomatis dan semua pesan (level DEBUG ke atas) ditulis ke sana.
        level: level minimum untuk handler konsol.
        logger_name: nama logger akar yang dikonfigurasi.

    Returns:
        Logger yang sudah terkonfigurasi, siap dipakai/di-`getChild()`.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    # Terminal Windows lawas (cp1252) bisa gagal encode karakter non-ASCII
    # tertentu yang muncul di pesan log (mis. simbol Unicode pada nama
    # senyawa). Reconfigure ke UTF-8 dengan errors="replace" supaya log
    # tidak pernah menggagalkan proses hanya karena satu karakter tak ter-encode.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass

    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(console)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Ambil child logger di bawah namespace ``chemflow``.

    Args:
        name: nama submodul, mis. ``"chem.ligand_preparer"``.

    Returns:
        Logger ``chemflow.<name>``.
    """
    return logging.getLogger(f"chemflow.{name}")
