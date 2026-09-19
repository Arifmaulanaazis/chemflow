"""
Pemeriksaan kesiapan mesin untuk chemflow.

Dipanggil dari ``chemflow init`` untuk melaporkan ke pengguna: paket Python
apa yang sudah/belum terpasang, apakah OpenBabel bisa ditemukan (satu-satunya
tool eksternal yang wajib diinstal manual oleh pengguna), versi AutoDock Vina
apa yang sudah tercache atau tersedia untuk auto-download, dan apakah layanan
jaringan yang dipakai pipeline (RCSB, PubChem, ADMETLab3, GitHub Releases)
bisa dijangkau dari mesin ini. Tidak ada pemeriksaan yang boleh menghentikan
proses; kegagalan satu pemeriksaan hanya dilaporkan, bukan raise.
"""

from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional

_REQUIRED_PACKAGES = [
    ("rdkit", "rdkit"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("requests", "requests"),
    ("bs4", "beautifulsoup4"),
    ("pubchempy", "pubchempy"),
    ("numpy", "numpy"),
    ("matplotlib", "matplotlib"),
    ("sklearn", "scikit-learn"),
]

_NETWORK_TARGETS = [
    ("RCSB (unduh struktur PDB)", "https://files.rcsb.org"),
    ("PubChem (resolusi SMILES)", "https://pubchem.ncbi.nlm.nih.gov"),
    ("ADMETLab3 (prediksi ADMET)", "https://admetlab3.scbdd.com"),
    ("GitHub Releases (auto-download Vina)", "https://api.github.com"),
]


@dataclass
class CheckResult:
    category: str
    name: str
    ok: bool
    detail: str
    hint: str = ""


def check_python_packages() -> List[CheckResult]:
    """Cek apakah setiap dependency Python di ``requirements.txt`` terpasang."""
    results = []
    for module_name, pip_name in _REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", "?")
            results.append(CheckResult("Paket Python", pip_name, True, f"terpasang (v{version})"))
        except ImportError:
            results.append(CheckResult(
                "Paket Python", pip_name, False, "tidak terpasang",
                hint=f"pip install {pip_name}",
            ))
    return results


def check_openbabel() -> CheckResult:
    """Cek apakah ``obabel`` bisa ditemukan di PATH (wajib diinstal manual oleh pengguna)."""
    exe = shutil.which("obabel") or shutil.which("obabel.exe")
    if not exe:
        return CheckResult(
            "Tool eksternal", "OpenBabel", False, "tidak ditemukan di PATH",
            hint="Install dari https://openbabel.org lalu pastikan folder binary-nya ada di PATH sistem.",
        )
    try:
        proc = subprocess.run([exe, "-V"], capture_output=True, text=True, timeout=10)
        version_line = (proc.stdout or proc.stderr or "?").strip().splitlines()[0]
        return CheckResult("Tool eksternal", "OpenBabel", True, f"ditemukan: {version_line} ({exe})")
    except Exception as exc:
        return CheckResult("Tool eksternal", "OpenBabel", True, f"ditemukan di {exe}, versi tak terbaca ({exc})")


def check_vina() -> List[CheckResult]:
    """Cek cache lokal AutoDock Vina & ketersediaan versi kompatibel di GitHub Releases."""
    from chemflow.docking.vina_manager import VinaReleaseManager

    results = []
    manager = VinaReleaseManager()
    cache_dir = manager._cache_dir  # noqa: SLF001 (dipakai hanya untuk melaporkan lokasi ke pengguna)

    cached = []
    if cache_dir.exists():
        cached = sorted(p.name for p in cache_dir.glob("vina_*") if p.is_file())

    if cached:
        results.append(CheckResult("AutoDock Vina", "Cache lokal", True,
                                     f"{len(cached)} binary tercache di {cache_dir}: {', '.join(cached)}"))
    else:
        results.append(CheckResult("AutoDock Vina", "Cache lokal", True,
                                     f"belum ada binary tercache di {cache_dir} (akan diunduh otomatis saat pipeline pertama kali jalan)"))

    try:
        compatible = manager.list_compatible()
        if compatible:
            versions = ", ".join(a.version for a in compatible[:5])
            results.append(CheckResult("AutoDock Vina", "GitHub Releases", True,
                                         f"{len(compatible)} versi kompatibel tersedia untuk diunduh: {versions}, ..."))
        else:
            results.append(CheckResult("AutoDock Vina", "GitHub Releases", False,
                                         "tidak ada versi kompatibel dengan OS/arsitektur mesin ini ditemukan"))
    except Exception as exc:
        results.append(CheckResult(
            "AutoDock Vina", "GitHub Releases", False, f"tidak bisa dihubungi saat ini ({exc})",
            hint="Tidak masalah jika sudah ada binary tercache atau akan pakai --vina-executable manual.",
        ))
    return results


def check_network() -> List[CheckResult]:
    """Cek jangkauan jaringan ke tiap layanan eksternal yang dipakai pipeline.

    ``verify=False`` hanya dipakai untuk ADMETLab3, satu-satunya layanan
    dengan sertifikat SSL yang diketahui bermasalah (lihat ``admetlab_scraper.py``).
    Layanan lain (RCSB, PubChem, GitHub) diverifikasi normal.
    """
    import requests

    results = []
    for label, url in _NETWORK_TARGETS:
        verify = "admetlab3" not in url
        try:
            requests.head(url, timeout=5, verify=verify)
            results.append(CheckResult("Jaringan", label, True, "terjangkau"))
        except Exception:
            try:
                requests.get(url, timeout=5, verify=verify)
                results.append(CheckResult("Jaringan", label, True, "terjangkau"))
            except Exception as exc:
                results.append(CheckResult(
                    "Jaringan", label, False, f"tidak terjangkau ({exc.__class__.__name__})",
                    hint="Fitur terkait tidak akan berfungsi tanpa koneksi ke layanan ini.",
                ))
    return results


def run_all_checks() -> List[CheckResult]:
    """Jalankan seluruh pemeriksaan kesiapan mesin. Tidak pernah raise."""
    results: List[CheckResult] = []
    results.append(CheckResult("Python", "Versi interpreter", sys.version_info >= (3, 9),
                                 f"{platform.python_version()} ({'OK' if sys.version_info >= (3, 9) else 'butuh >= 3.9'})"))
    results.extend(check_python_packages())
    results.append(check_openbabel())
    results.extend(check_vina())
    results.extend(check_network())
    return results


def format_report(results: List[CheckResult]) -> str:
    """Format daftar ``CheckResult`` menjadi teks laporan siap-cetak."""
    lines = ["", "=== Pemeriksaan Kesiapan Mesin chemflow ===", ""]
    current_category: Optional[str] = None
    n_fail = 0
    for r in results:
        if r.category != current_category:
            lines.append(f"[{r.category}]")
            current_category = r.category
        mark = "OK " if r.ok else "!! "
        lines.append(f"  {mark} {r.name}: {r.detail}")
        if not r.ok and r.hint:
            lines.append(f"       -> {r.hint}")
        if not r.ok:
            n_fail += 1

    lines.append("")
    if n_fail == 0:
        lines.append("Semua pemeriksaan lolos. Pipeline siap dijalankan.")
    else:
        lines.append(f"{n_fail} hal butuh perhatian (lihat tanda '!!' di atas).")
    lines.append("")
    return "\n".join(lines)
