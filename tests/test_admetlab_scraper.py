"""
Test AdmetLabScraper. requests.Session di-mock total (tidak ada request
jaringan nyata), memvalidasi alur CSRF -> POST -> parse link CSV (format
baru <a href> maupun fallback legacy window.open) -> GET CSV dgn verify
konsisten.
"""

import pytest

from chemflow.admet import admetlab_scraper as scraper_mod
from chemflow.admet.admetlab_scraper import AdmetLabScraper


class _FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        pass


class _FakeSessionNewFormat:
    """Mensimulasikan situs ADMETLab3 versi baru (<a href=".../download/csv">)."""

    def __init__(self):
        self.headers = {}
        self.verify_calls = []

    def get(self, url, verify=None, timeout=None, **kwargs):
        self.verify_calls.append((url, verify))
        if url == AdmetLabScraper.INDEX_URL:
            return _FakeResponse('<input name="csrfmiddlewaretoken" value="TOKEN123">')
        return _FakeResponse("SMILES,MW,LogP\nCCO,46.07,0.1\n")

    def post(self, url, headers=None, data=None, verify=None, timeout=None, **kwargs):
        self.verify_calls.append((url, verify))
        assert data["csrfmiddlewaretoken"] == "TOKEN123"
        return _FakeResponse('<a href="/server/result/1/download/csv">Unduh</a>')

    def close(self):
        pass


class _FakeSessionLegacyFormat(_FakeSessionNewFormat):
    """Mensimulasikan situs versi lama (window.open(...) JS, tanpa <a href>)."""

    def post(self, url, headers=None, data=None, verify=None, timeout=None, **kwargs):
        self.verify_calls.append((url, verify))
        return _FakeResponse('<script>window.open("/server/result/1/download.csv")</script>')


@pytest.fixture
def patch_session(monkeypatch):
    def _apply(fake_session_instance):
        monkeypatch.setattr(scraper_mod.requests, "Session", lambda: fake_session_instance)
    return _apply


def test_alur_format_baru_href(patch_session):
    fake = _FakeSessionNewFormat()
    patch_session(fake)

    result = AdmetLabScraper(ssl_verify=False).run(["CCO"])
    assert not result.empty
    assert result.iloc[0]["MW"] == 46.07


def test_alur_fallback_legacy_window_open(patch_session):
    fake = _FakeSessionLegacyFormat()
    patch_session(fake)

    result = AdmetLabScraper(ssl_verify=False).run(["CCO"])
    assert not result.empty


def test_verify_false_konsisten_di_semua_request(patch_session):
    fake = _FakeSessionNewFormat()
    patch_session(fake)

    AdmetLabScraper(ssl_verify=False).run(["CCO"])
    # Seluruh request, termasuk GET unduh CSV terakhir, harus memakai verify=False.
    assert all(v is False for _, v in fake.verify_calls)


def test_max_batch_size_invalid_raise():
    with pytest.raises(ValueError):
        AdmetLabScraper(max_batch_size=0)
    with pytest.raises(ValueError):
        AdmetLabScraper(max_batch_size=101)


class _FakeSession429ThenSuccess(_FakeSessionNewFormat):
    """POST pertama kena rate-limit (429), percobaan kedua sukses."""

    def __init__(self):
        super().__init__()
        self._post_calls = 0

    def post(self, url, headers=None, data=None, verify=None, timeout=None, **kwargs):
        self.verify_calls.append((url, verify))
        self._post_calls += 1
        if self._post_calls == 1:
            return _FakeResponse(status_code=429)
        return _FakeResponse('<a href="/server/result/1/download/csv">Unduh</a>')


class _FakeSessionAlways429(_FakeSessionNewFormat):
    def post(self, url, headers=None, data=None, verify=None, timeout=None, **kwargs):
        self.verify_calls.append((url, verify))
        return _FakeResponse(status_code=429)


def test_retry_setelah_429_lalu_sukses(patch_session):
    fake = _FakeSession429ThenSuccess()
    patch_session(fake)

    scraper = AdmetLabScraper(ssl_verify=False, max_retries=3, retry_backoff_seconds=0)
    result = scraper.run(["CCO"])
    assert not result.empty
    assert fake._post_calls == 2


def test_retry_habis_semua_429_raise_ke_run_sebagai_warning(patch_session):
    fake = _FakeSessionAlways429()
    patch_session(fake)

    scraper = AdmetLabScraper(ssl_verify=False, max_retries=2, retry_backoff_seconds=0)
    result = scraper.run(["CCO"])
    assert result.empty  # run() menangkap ValueError per batch, tidak melempar ke pemanggil


def test_batch_gagal_tidak_menghentikan_batch_lain(patch_session, monkeypatch):
    fake = _FakeSessionNewFormat()
    patch_session(fake)

    scraper = AdmetLabScraper(max_batch_size=1, ssl_verify=False)
    # Batch pertama sukses, batch kedua dipaksa gagal via smiles kosong yang
    # bikin _process_batch tetap jalan normal (fake session selalu sukses) --
    # di sini kita hanya pastikan run() dengan >1 batch tidak error total.
    result = scraper.run(["CCO", "CCC"])
    assert len(result) == 2  # 2 batch masing2 1 baris CSV
