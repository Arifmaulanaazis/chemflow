"""
Pembungkus subprocess yang seragam untuk memanggil executable eksternal
(OpenBabel, AutoDock Vina) lintas platform.

Dua kebutuhan utama yang mendorong modul ini:
  1. Di Windows, proses child tanpa flag khusus akan memunculkan jendela
     konsol baru yang mengganggu. ``CREATE_NO_WINDOW`` mencegah itu, tapi
     flag ini hanya ada/berlaku di Windows.
  2. AutoDock Vina versi >1.1.2 tidak lagi mendukung argumen ``--log``,
     sehingga log harus ditangkap dari stdout secara streaming (bukan
     mengandalkan file log yang ditulis Vina sendiri) dan disimpan manual.
     Fungsi ``stream_process`` di sini dipakai baik oleh OpenBabel (non-
     streaming, cukup ``run_capture``) maupun Vina (streaming baris-per-baris).
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence

_IS_WINDOWS = platform.system() == "Windows"


def _creation_flags() -> int:
    """Flag subprocess yang menekan jendela konsol baru di Windows."""
    if _IS_WINDOWS:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def run_capture(
    cmd: Sequence[str],
    cwd: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """Jalankan perintah dan tangkap stdout/stderr sekaligus (non-streaming).

    Dipakai untuk tool yang selesai cepat dan tak perlu progres real-time
    (mis. OpenBabel per-file conversion).

    Args:
        cmd: argv perintah.
        cwd: direktori kerja proses child.
        timeout: batas waktu detik, ``None`` = tanpa batas.

    Returns:
        ``subprocess.CompletedProcess`` (tidak raise otomatis, cek
        ``.returncode`` di pemanggil untuk pesan error yang lebih spesifik).
    """
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_creation_flags(),
    )


def stream_process(
    cmd: Sequence[str],
    cwd: Optional[Path] = None,
    on_line: Optional[Callable[[str], None]] = None,
    echo: bool = False,
) -> tuple[int, List[str]]:
    """Jalankan perintah, tangkap stdout+stderr baris-per-baris secara live.

    Dipakai untuk AutoDock Vina: tidak ada argumen ``--log`` yang bisa
    diandalkan di versi modern, jadi seluruh output ditangkap di sini dan
    disimpan manual oleh pemanggil (lihat ``docking/vina_runner.py``).

    Args:
        cmd: argv perintah.
        cwd: direktori kerja proses child.
        on_line: callback opsional dipanggil untuk tiap baris (tanpa newline
            akhir), berguna untuk progress bar / streaming ke UI lain.
        echo: jika True, cetak tiap baris ke stdout proses ini juga.

    Returns:
        Tuple ``(return_code, semua_baris_termasuk_newline)``.
    """
    popen_kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(cwd) if cwd else None,
        creationflags=_creation_flags(),
    )
    proc = subprocess.Popen(list(cmd), **popen_kwargs)

    lines: List[str] = []
    try:
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                continue
            lines.append(line)
            if echo:
                print(f"    {line}", end="", flush=True)
            if on_line:
                on_line(line.rstrip("\n"))

        ret = proc.wait()
    except BaseException:
        # Ctrl+C / error: proses anak berkonsol tersembunyi (CREATE_NO_WINDOW) tidak menerima
        # sinyal itu dan akan jadi proses yatim yang terus menulis keluaran, jadi matikan di sini.
        proc.kill()
        proc.wait()
        raise
    return ret, lines
