"""
Resolusi SMILES dari nama senyawa lewat PubChem (PubChemPy), dipakai saat
Excel input hanya berisi nama senyawa tanpa SMILES.

Cache in-memory + retry ringan dengan backoff untuk menangani rate-limit
PubChem (HTTP 503/429 sering muncul saat query beruntun). Kegagalan resolusi
satu nama TIDAK menghentikan pipeline. Di terminal interaktif, pengguna
ditawari mengetik SMILES manual atau melewati senyawa itu (lihat
``prompt_manual_smiles``); di luar terminal interaktif, senyawa itu
langsung dilewati dan dicatat di ringkasan akhir, sisanya tetap diproses.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Dict, Optional


class PubChemResolver:
    """Resolver nama-senyawa -> SMILES via PubChem, dengan cache per run."""

    def __init__(self, max_retries: int = 3, retry_backoff_sec: float = 2.0,
                 logger: Optional[logging.Logger] = None) -> None:
        self._max_retries = max_retries
        self._retry_backoff_sec = retry_backoff_sec
        self._cache: Dict[str, Optional[str]] = {}
        self._log = logger or logging.getLogger(__name__)

    def resolve(self, name: str) -> Optional[str]:
        """Cari SMILES isomerik untuk satu nama senyawa.

        Args:
            name: nama senyawa (nama dagang/IUPAC/umum, apa pun yang bisa
                dicari PubChem berdasar nama).

        Returns:
            SMILES isomerik (fallback ke kanonik jika isomerik tak ada),
            atau ``None`` jika senyawa tak ditemukan / semua percobaan gagal.
        """
        key = name.strip().lower()
        if key in self._cache:
            return self._cache[key]

        smiles = self._query_with_retry(name)
        self._cache[key] = smiles
        if smiles:
            self._log.info(f"[PubChem] '{name}' -> {smiles}")
        else:
            self._log.warning(f"[PubChem] '{name}' tidak ditemukan / gagal di-resolve.")
        return smiles

    def _query_with_retry(self, name: str) -> Optional[str]:
        try:
            import pubchempy as pcp  # type: ignore
        except ImportError:
            self._log.error("Paket 'pubchempy' tidak terpasang. Jalankan: pip install pubchempy")
            return None

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                compounds = pcp.get_compounds(name, "name")
                if not compounds:
                    return None
                compound = compounds[0]
                # PubChemPy terbaru: `.smiles` (isomeric). `.isomeric_smiles`/`.canonical_smiles`
                # deprecated tapi dipertahankan sbg fallback utk versi pubchempy lebih lama.
                smiles = (
                    getattr(compound, "smiles", None)
                    or getattr(compound, "isomeric_smiles", None)
                    or getattr(compound, "canonical_smiles", None)
                )
                return smiles
            except Exception as exc:  # noqa: BLE001 (PubChemPy melempar beragam tipe exception)
                last_exc = exc
                if attempt < self._max_retries:
                    wait = self._retry_backoff_sec * attempt
                    self._log.debug(f"[PubChem] Percobaan {attempt} gagal ({exc}); tunggu {wait:.0f}s.")
                    time.sleep(wait)

        self._log.warning(f"[PubChem] Semua percobaan gagal untuk '{name}': {last_exc}")
        return None


def prompt_manual_smiles(name: str) -> Optional[str]:
    """Tanya pengguna secara interaktif untuk mengisi SMILES manual atau
    melewati senyawa yang gagal di-resolve dari PubChem.

    Divalidasi via RDKit sebelum diterima. Mengulang prompt kalau SMILES
    yang dimasukkan tidak valid.

    Args:
        name: nama senyawa yang gagal ditemukan di PubChem.

    Returns:
        SMILES valid yang dimasukkan pengguna, atau ``None`` jika pengguna
        memilih melewati senyawa ini.

    Raises:
        RuntimeError: tidak ada terminal interaktif (stdin non-TTY). Pemanggil
            harus menangkap ini dan melewati senyawa tanpa prompt.
    """
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Fallback SMILES manual diminta, tapi tidak ada terminal interaktif "
            "(stdin non-TTY)."
        )

    from rdkit import Chem

    print(f"\n  [!] SMILES untuk '{name}' tidak ditemukan di PubChem.")
    while True:
        raw = input("      Masukkan SMILES manual (kosongkan / ketik 's' untuk skip): ").strip()
        if not raw or raw.lower() in ("s", "skip"):
            print(f"      Melewati '{name}'.\n")
            return None
        if Chem.MolFromSmiles(raw) is not None:
            print(f"      [OK] SMILES diterima untuk '{name}'.\n")
            return raw
        print("      [!] SMILES tidak valid, coba lagi atau ketik 's' untuk skip.")
