"""
Manajer AutoDock Vina. Resolusi & auto-download binary yang cocok untuk
mesin pengguna langsung dari GitHub Releases
(https://github.com/ccsb-scripps/AutoDock-Vina/releases), tanpa
mengharuskan pengguna mengunduh executable secara manual.

Kenapa ini butuh penanganan khusus (bukan 1 pola regex sederhana): skema
penamaan asset Vina berubah beberapa kali sepanjang sejarah rilisnya, dan
tidak semua versi mendukung Windows:

    v1.1.2-boost-new       : hanya Linux (vina_1.1.2-boost-new_linux_x86_64)
    v1.2.0 sampai v1.2.2   : hanya Linux/macOS, tanpa Windows
    v1.2.3                 : Windows GitHub pertama (vina_1.2.3_windows_x86_64.exe)
    v1.2.4 dan seterusnya  : skema "current" (vina_{ver}_win.exe,
                             vina_{ver}_linux_{x86_64,aarch64},
                             vina_{ver}_mac_{x86_64,aarch64})

Deteksi memakai daftar pola regex (bukan template tunggal) yang dicoba
berurutan per nama asset, tahan terhadap era penamaan mana pun tanpa perlu tahu
versi rilis sebelumnya.
"""

from __future__ import annotations

import logging
import platform
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests

_GITHUB_API_RELEASES = "https://api.github.com/repos/ccsb-scripps/AutoDock-Vina/releases"

# (regex nama asset, os_normalized, arch_normalized). Urutan penting,
# pola lebih spesifik lebih dulu. os in {"windows","linux","darwin"},
# arch in {"x86_64","aarch64"}.
_ASSET_PATTERNS: List[tuple] = [
    (re.compile(r"^vina_[\d.]+(?:\.dev\d+)?_win\.exe$"), "windows", "x86_64"),
    (re.compile(r"^vina_[\d.]+_windows_x86_64\.exe$"), "windows", "x86_64"),
    (re.compile(r"^vina_[\d.]+(?:\.dev\d+)?_linux_x86_64$"), "linux", "x86_64"),
    (re.compile(r"^vina_[\d.]+_linux_aarch64$"), "linux", "aarch64"),
    (re.compile(r"^vina_[\d.\-a-zA-Z]+_linux_x86_64$"), "linux", "x86_64"),  # varian tag "1.1.2-boost-new"
    (re.compile(r"^vina_[\d.]+(?:\.dev\d+)?_macos_x86_64$"), "darwin", "x86_64"),
    (re.compile(r"^vina_[\d.]+_macos_arm64$"), "darwin", "aarch64"),
    (re.compile(r"^vina_[\d.]+_mac_x86_64$"), "darwin", "x86_64"),
    (re.compile(r"^vina_[\d.]+_mac_aarch64$"), "darwin", "aarch64"),
]


@dataclass
class VinaAsset:
    """Satu binary Vina yang tersedia untuk diunduh."""
    version: str
    os_name: str
    arch: str
    filename: str
    download_url: str

    @property
    def label(self) -> str:
        return f"Vina {self.version} ({self.os_name}/{self.arch})"


def _host_os() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def _host_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        return "x86_64"
    if machine in ("arm64", "aarch64"):
        return "aarch64"
    return machine


class VinaReleaseManager:
    """Menemukan, memfilter, mengunduh, dan menyimpan cache binary AutoDock Vina."""

    def __init__(self, cache_dir: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
        self._cache_dir = cache_dir or (Path.home() / ".cache" / "chemflow" / "vina")
        self._log = logger or logging.getLogger(__name__)

    def list_remote_assets(self) -> List[VinaAsset]:
        """Ambil & klasifikasikan seluruh asset dari GitHub Releases API.

        Returns:
            Semua asset yang berhasil diklasifikasikan (versi+OS+arch).
            Asset yang tak dikenali polanya (mis. ``vina_split_*``,
            checksum) dilewati diam-diam.

        Raises:
            RuntimeError: request ke GitHub API gagal.
        """
        try:
            resp = requests.get(_GITHUB_API_RELEASES, timeout=30, headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Gagal mengambil daftar rilis AutoDock Vina dari GitHub: {exc}") from exc

        assets: List[VinaAsset] = []
        for release in resp.json():
            tag = str(release.get("tag_name", "")).lstrip("v")
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if "split" in name or name.endswith((".md5", ".sha256", ".txt")):
                    continue
                classified = self._classify(name)
                if classified is None:
                    continue
                os_name, arch = classified
                assets.append(VinaAsset(
                    version=self._version_from_name(name) or tag,
                    os_name=os_name, arch=arch, filename=name,
                    download_url=asset.get("browser_download_url", ""),
                ))
        return assets

    def list_compatible(self) -> List[VinaAsset]:
        """Asset yang cocok dengan OS+arsitektur mesin ini, terurut versi terbaru dulu."""
        host_os, host_arch = _host_os(), _host_arch()
        compatible = [a for a in self.list_remote_assets() if a.os_name == host_os and a.arch == host_arch]
        compatible.sort(key=lambda a: self._version_key(a.version), reverse=True)
        return compatible

    def resolve(self, version: Optional[str] = None) -> Path:
        """Dapatkan path executable Vina siap pakai, dari cache lokal,
        atau unduh dari GitHub Releases jika belum ada.

        Path yang dikembalikan selalu absolut dan langsung dieksekusi oleh
        pemanggil; tidak ada ketergantungan pada PATH sistem di jalur mana pun.

        Args:
            version: versi spesifik (mis. "1.2.5"). ``None`` = pilih versi
                terbaru yang kompatibel dengan mesin ini.

        Returns:
            Path absolut ke executable Vina (sudah diberi izin eksekusi di POSIX).

        Raises:
            RuntimeError: tidak ada versi kompatibel ditemukan (mis. Windows
                dgn versi 1.2.0-1.2.2 yang memang tidak menyediakan build Windows),
                atau GitHub Releases tidak terjangkau dan tidak ada cache sama sekali.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        cached = self._find_cached(version)
        if cached is not None:
            self._log.info(f"Memakai Vina dari cache: {cached}")
            return cached

        try:
            compatible = self.list_compatible()
        except RuntimeError as exc:
            if version is None:
                fallback = self._find_cached(None)
                if fallback is not None:
                    self._log.warning(
                        f"GitHub Releases tidak terjangkau ({exc}); memakai versi "
                        f"tercache yang tersedia sebagai fallback: {fallback.name}"
                    )
                    return fallback
            raise

        if not compatible:
            raise RuntimeError(
                f"Tidak ada binary AutoDock Vina yang kompatibel dengan mesin ini "
                f"({_host_os()}/{_host_arch()}) ditemukan di GitHub Releases. "
                f"Versi 1.2.0-1.2.2 diketahui tidak menyediakan build Windows, coba versi >=1.2.3."
            )

        chosen = next((a for a in compatible if a.version == version), None) if version else compatible[0]
        if chosen is None:
            available = ", ".join(a.version for a in compatible)
            raise RuntimeError(
                f"Versi Vina '{version}' tidak tersedia untuk mesin ini. "
                f"Versi yang kompatibel: {available}"
            )

        return self._download(chosen)

    def _download(self, asset: VinaAsset) -> Path:
        dest = self._cache_dir / self._cache_filename(asset)
        self._log.info(f"Mengunduh {asset.label} dari {asset.download_url} ...")
        resp = requests.get(asset.download_url, timeout=300, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                f.write(chunk)

        if platform.system() != "Windows":
            current = dest.stat().st_mode
            dest.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        self._log.info(f"Vina {asset.version} tersimpan: {dest}")
        return dest

    def _find_cached(self, version: Optional[str]) -> Optional[Path]:
        """Cari binary tercache, ranking numerik (tuple versi), bukan string sort."""
        if not self._cache_dir.exists():
            return None
        ranked = []
        for path in self._cache_dir.glob("vina_*"):
            if not path.is_file():
                continue
            cached_version = self._parse_cached_version(path.name)
            if cached_version is None:
                continue
            if version is not None and cached_version != version:
                continue
            ranked.append((self._version_key(cached_version), path))
        if not ranked:
            return None
        ranked.sort(key=lambda t: t[0], reverse=True)
        return ranked[0][1]

    @staticmethod
    def _parse_cached_version(filename: str) -> Optional[str]:
        m = re.match(r"^vina_(.+)_(windows|linux|darwin)_(x86_64|aarch64)(?:\.exe)?$", filename)
        return m.group(1) if m else None

    @staticmethod
    def _cache_filename(asset: VinaAsset) -> str:
        suffix = ".exe" if asset.os_name == "windows" else ""
        return f"vina_{asset.version}_{asset.os_name}_{asset.arch}{suffix}"

    @staticmethod
    def _classify(filename: str) -> Optional[tuple]:
        for pattern, os_name, arch in _ASSET_PATTERNS:
            if pattern.match(filename):
                return os_name, arch
        return None

    @staticmethod
    def _version_from_name(filename: str) -> Optional[str]:
        m = re.search(r"vina_([\d.]+(?:\.dev\d+)?(?:-[a-zA-Z0-9]+)?)_", filename)
        return m.group(1) if m else None

    @staticmethod
    def _version_key(version: str) -> tuple:
        """Kunci pengurutan versi yang toleran terhadap suffix non-numerik
        (mis. "1.2.0.dev3", "1.1.2-boost-new")."""
        base = re.split(r"[-]", version)[0]
        parts = re.findall(r"\d+", base)
        return tuple(int(p) for p in parts) if parts else (0,)
