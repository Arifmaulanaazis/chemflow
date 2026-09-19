"""
Scraper ADMETLab3 (https://admetlab3.scbdd.com) untuk prediksi ADMET dari SMILES.

Alur: GET halaman index (ambil token CSRF Django) -> POST daftar SMILES
(server menjalankan model ADMET secara SINKRON sebelum merespons, bisa
>20 detik untuk satu batch, jadi read-timeout dibuat longgar) -> cari link
unduh CSV di HTML hasil (situs ini pernah menyisipkan URL CSV lewat
`window.open(...)` di dalam <script>, sekarang lewat `<a href="...">`
biasa, dua-duanya ditangani) -> unduh CSV.

``verify=False`` dipakai konsisten di seluruh request karena sertifikat
SSL ADMETLab3 kadang bermasalah/self-signed.

Situs ini kadang merespons HTTP 429 (rate-limit) walau untuk batch kecil.
HTTP 429/5xx dan timeout dicoba ulang otomatis dengan backoff linier
sebelum benar-benar gagal.
"""

from __future__ import annotations

import logging
import re
import time
from io import StringIO
from typing import List, Optional, Union
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class _RetryableHttpError(Exception):
    """Error HTTP transient (rate-limit/server sibuk), aman dicoba ulang."""


class AdmetLabScraper:
    """Klien scraping ADMETLab3 untuk prediksi ADMET dari daftar SMILES."""

    BASE_URL = "https://admetlab3.scbdd.com"
    INDEX_URL = f"{BASE_URL}/server/screening"
    POST_URL = f"{BASE_URL}/server/screeningCal"

    def __init__(self, max_batch_size: int = 50, ssl_verify: bool = False,
                 logger: Optional[logging.Logger] = None,
                 max_retries: int = 5, retry_backoff_seconds: float = 10.0) -> None:
        if not (1 <= max_batch_size <= 100):
            raise ValueError("max_batch_size harus di rentang [1, 100] (batas server ADMETLab3).")
        self._batch_size = max_batch_size
        self._verify = ssl_verify
        self._log = logger or logging.getLogger(__name__)
        self._max_retries = max(1, max_retries)
        self._retry_backoff = retry_backoff_seconds

    def run(self, smiles_input: Union[str, List[str]]) -> pd.DataFrame:
        """Jalankan prediksi ADMET untuk satu/daftar SMILES, dibatch otomatis.

        Args:
            smiles_input: satu string SMILES atau daftar SMILES.

        Returns:
            DataFrame gabungan semua batch (kolom persis header CSV
            ADMETLab3 apa adanya, bisa berubah sewaktu API mereka berubah).
            DataFrame kosong jika seluruh batch gagal.
        """
        smiles_list = [smiles_input] if isinstance(smiles_input, str) else list(smiles_input)

        results: List[pd.DataFrame] = []
        for i in range(0, len(smiles_list), self._batch_size):
            batch = smiles_list[i:i + self._batch_size]
            try:
                df = self._process_batch(batch)
                if not df.empty:
                    results.append(df)
            except ValueError as exc:
                self._log.warning(f"[ADMETLab3] Batch {i // self._batch_size + 1} gagal: {exc}")

        if results:
            return pd.concat(results, ignore_index=True)
        return pd.DataFrame()

    def _process_batch(self, smiles_batch: List[str]) -> pd.DataFrame:
        last_exc: Exception = ValueError("ADMETLab3 gagal tanpa detail error.")
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._process_batch_once(smiles_batch)
            except (requests.exceptions.Timeout, _RetryableHttpError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    wait = self._retry_backoff * attempt
                    self._log.warning(
                        f"[ADMETLab3] Percobaan {attempt}/{self._max_retries} gagal ({exc}), "
                        f"server sedang sibuk/rate-limit, mencoba lagi dalam {wait:.0f} detik ..."
                    )
                    time.sleep(wait)
        raise ValueError(str(last_exc)) from last_exc

    def _process_batch_once(self, smiles_batch: List[str]) -> pd.DataFrame:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        try:
            token = self._get_csrf_token(session)
            smiles_text = "\r\n".join(smiles_batch)
            response = self._submit_smiles(session, smiles_text, token)
            self._check_retryable(response)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            csv_url = self._get_csv_url(soup)
            if not csv_url:
                self._log.warning("[ADMETLab3] Link unduh CSV tidak ditemukan di halaman hasil.")
                return pd.DataFrame()

            csv_response = session.get(csv_url, verify=self._verify, timeout=(10, 60))
            self._check_retryable(csv_response)
            csv_response.raise_for_status()
            return pd.read_csv(StringIO(csv_response.text))
        except (requests.exceptions.Timeout, _RetryableHttpError):
            raise
        except requests.exceptions.RequestException as exc:
            raise ValueError(f"Error jaringan mengakses ADMETLab3: {exc}") from exc
        finally:
            session.close()

    def _check_retryable(self, response: requests.Response) -> None:
        if response.status_code in _RETRYABLE_STATUS:
            raise _RetryableHttpError(f"HTTP {response.status_code} dari ADMETLab3 (rate-limit/server sibuk)")

    def _get_csrf_token(self, session: requests.Session) -> str:
        try:
            response = session.get(self.INDEX_URL, verify=self._verify, timeout=(10, 30))
            self._check_retryable(response)
            response.raise_for_status()
        except (requests.exceptions.Timeout, _RetryableHttpError):
            raise
        except requests.exceptions.RequestException as exc:
            raise ValueError(f"Error jaringan memuat index ADMETLab3: {exc}") from exc

        soup = BeautifulSoup(response.text, "html.parser")
        token_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
        if not token_input:
            raise ValueError("Token CSRF tidak ditemukan di halaman index ADMETLab3.")
        return token_input["value"]

    def _submit_smiles(self, session: requests.Session, smiles_text: str, token: str) -> requests.Response:
        headers = {
            "Referer": self.INDEX_URL,
            "Origin": self.BASE_URL,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"csrfmiddlewaretoken": token, "smiles-list": smiles_text, "method": "2"}
        # Endpoint ini menjalankan model ADMET SINKRON di server sebelum
        # merespons, bisa >20 detik untuk satu batch, jadi read-timeout
        # dibuat longgar (connect tetap ketat).
        return session.post(self.POST_URL, headers=headers, data=data, verify=self._verify, timeout=(10, 180))

    def _get_csv_url(self, soup: BeautifulSoup) -> Optional[str]:
        link = soup.find("a", href=re.compile(r"/download/csv/?$"))
        if link and link.get("href"):
            return urljoin(self.BASE_URL, link["href"])

        # Fallback legacy: versi lama situs menyisipkan URL CSV lewat window.open() di <script>.
        for script in soup.find_all("script"):
            if script.string:
                match = re.search(r'window\.open\(["\'](.*?)(?:\.csv)["\']\)', script.string)
                if match:
                    return urljoin(self.BASE_URL, match.group(1) + ".csv")
        return None
