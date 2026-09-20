"""
Deteksi instalasi BIOVIA Discovery Studio dan peluncurannya dari Python.

BIOVIA memuat modul lisensinya (``ls_license64_vs2017``) lewat PATH yang
diisi Windows dari nilai ``Path`` di kunci registry ``App Paths``. Nilai itu
hanya ikut ketika aplikasi dibuka lewat shell (klik ganda, ``os.startfile``);
``subprocess.Popen`` biasa tidak membawanya sehingga BIOVIA berhenti dengan
pesan "licensing problem" padahal lisensinya sah. ``launch_environment``
menambahkan direktori itu ke PATH proses yang diluncurkan.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

_EXE_RE = re.compile(r"^DiscoveryStudio(\d{4})\.exe$", re.IGNORECASE)
_FOLDER_RE = re.compile(r"^Discovery Studio\b.*?(\d{4})\s*$", re.IGNORECASE)
_APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"


class BioviaUnavailableError(RuntimeError):
    """BIOVIA tidak bisa dipakai: bukan Windows, tidak terpasang, atau dependensi otomasi kurang."""


@dataclass(frozen=True)
class BioviaInstallation:
    """Satu instalasi Discovery Studio yang executable-nya ada."""
    year: int
    executable: Path


def _registry_reader(subkey: str) -> Optional[Dict[str, str]]:
    """Baca nilai string sebuah kunci registry (HKLM 64-bit, HKLM 32-bit, lalu HKCU)."""
    if sys.platform != "win32":
        return None
    import winreg

    for hive, view in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                       (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as key:
                values: Dict[str, str] = {}
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    if isinstance(value, str):
                        values[name] = os.path.expandvars(value)
                    index += 1
                return values
        except OSError:
            continue
    return None


def _registry_subkeys(subkey: str) -> List[str]:
    """Nama sub-kunci di bawah ``subkey`` pada tiga lokasi registry yang sama."""
    if sys.platform != "win32":
        return []
    import winreg

    names: List[str] = []
    for hive, view in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                       (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as key:
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
        except OSError:
            continue
    return names


def _program_files_dirs() -> List[Path]:
    """Folder BIOVIA di Program Files (64-bit dan 32-bit), tanpa duplikat."""
    roots = [os.environ.get(name) for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
    roots += [r"C:\Program Files", r"C:\Program Files (x86)"]
    seen: List[Path] = []
    for root in roots:
        if root:
            candidate = Path(root) / "BIOVIA"
            if candidate not in seen:
                seen.append(candidate)
    return seen


def automation_dependencies_ok() -> bool:
    """True bila platform Windows dan paket otomasi (pywinauto, pyperclip, psutil, pywin32, Pillow) terpasang."""
    if sys.platform != "win32":
        return False
    import importlib.util

    return all(importlib.util.find_spec(name) is not None
               for name in ("pywinauto", "pyperclip", "psutil", "win32gui", "PIL"))


def detect_biovia(explicit: Optional[Path] = None, locator: Optional["BioviaLocator"] = None) -> Optional[Path]:
    """Executable BIOVIA bila otomasinya bisa berjalan di mesin ini, kalau tidak ``None``.

    Dipakai untuk memutuskan apakah similaritas dijalankan otomatis: butuh Windows,
    paket otomasi, dan instalasi Discovery Studio (atau ``explicit`` yang valid).
    """
    if not automation_dependencies_ok():
        return None
    try:
        return (locator or BioviaLocator()).find_executable(explicit)
    except FileNotFoundError:
        return None


class BioviaLocator:
    """Cari instalasi BIOVIA. Sumber registry dan folder bisa diganti untuk pengujian."""

    def __init__(self, base_dirs: Optional[Sequence[Path]] = None,
                 registry: Callable[[str], Optional[Dict[str, str]]] = _registry_reader,
                 registry_keys: Callable[[str], List[str]] = _registry_subkeys) -> None:
        self._base_dirs = list(base_dirs) if base_dirs is not None else _program_files_dirs()
        self._registry = registry
        self._registry_keys = registry_keys

    def installations(self) -> List[BioviaInstallation]:
        """Semua instalasi yang executable-nya ada, dari tahun terbaru ke terlama.

        Folder tanpa ``bin`` (sisa instalasi yang gagal) tidak dihitung.
        """
        found: Dict[Path, BioviaInstallation] = {}

        for name in self._registry_keys(_APP_PATHS):
            match = _EXE_RE.match(name)
            if not match:
                continue
            raw = (self._registry(f"{_APP_PATHS}\\{name}") or {}).get("", "")
            if raw and Path(raw).is_file():
                found[Path(raw).resolve()] = BioviaInstallation(int(match.group(1)), Path(raw))

        for base in self._base_dirs:
            if not base.is_dir():
                continue
            for folder in sorted(base.iterdir()):
                match = _FOLDER_RE.match(folder.name)
                if not match or not (folder / "bin").is_dir():
                    continue
                for exe in sorted((folder / "bin").iterdir()):
                    exe_match = _EXE_RE.match(exe.name)
                    if exe_match and exe.is_file():
                        found[exe.resolve()] = BioviaInstallation(int(exe_match.group(1)), exe)

        return sorted(found.values(), key=lambda item: (-item.year, str(item.executable)))

    def find_executable(self, explicit: Optional[Path] = None) -> Optional[Path]:
        """Jalur eksplisit bila ada, kalau tidak instalasi terbaru; ``None`` bila tidak ditemukan.

        Jalur eksplisit boleh berupa berkas .exe, folder ``bin``, atau folder instalasi.

        Raises:
            FileNotFoundError: jalur eksplisit tidak menunjuk executable Discovery Studio.
        """
        if explicit is not None:
            explicit = Path(explicit)
            if explicit.is_file():
                return explicit
            for folder in (explicit, explicit / "bin"):
                if folder.is_dir():
                    matches = sorted(p for p in folder.iterdir() if _EXE_RE.match(p.name) and p.is_file())
                    if matches:
                        return matches[-1]
            raise FileNotFoundError(f"Executable BIOVIA tidak ditemukan: {explicit}")
        installs = self.installations()
        return installs[0].executable if installs else None

    def app_paths(self, executable: Path) -> List[Path]:
        """Direktori yang ditambahkan Windows ke PATH saat aplikasi dibuka lewat shell.

        Diambil dari registry ``App Paths``; bila kuncinya tidak ada dipakai
        folder executable dan folder LicensePack bersama BIOVIA.
        """
        values = self._registry(f"{_APP_PATHS}\\{executable.name}")
        raw = (values or {}).get("Path", "")
        dirs = [Path(part) for part in raw.split(os.pathsep) if part.strip()]
        if dirs:
            return dirs
        dirs = [executable.parent]
        for root in (os.environ.get("CommonProgramFiles(x86)"), os.environ.get("CommonProgramFiles")):
            if root:
                shared = Path(root) / "BIOVIA" / "LicensePack"
                if shared.is_dir():
                    dirs.append(shared)
        return dirs

    def launch_environment(self, executable: Path) -> Dict[str, str]:
        """Salinan environment saat ini dengan direktori App Paths di depan PATH."""
        env = dict(os.environ)
        extra = [str(p) for p in self.app_paths(executable)]
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
        return env

    def launch(self, executable: Path) -> "subprocess.Popen":
        """Jalankan BIOVIA sebagai proses terpisah dengan environment yang benar."""
        return subprocess.Popen(
            [str(executable)], env=self.launch_environment(executable), cwd=str(executable.parent),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
