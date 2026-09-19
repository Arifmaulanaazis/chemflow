"""
Test VinaReleaseManager. GitHub API di-mock (tidak ada request jaringan
nyata), memvalidasi klasifikasi asset per era penamaan & filter OS/arch.
"""

import pytest

from chemflow.docking import vina_manager as vm


def _asset(name, url="https://example.com/" + "x"):
    return {"name": name, "browser_download_url": f"https://example.com/{name}"}


def _release(tag, asset_names):
    return {"tag_name": tag, "assets": [_asset(n) for n in asset_names]}


_FAKE_RELEASES_JSON = [
    _release("v1.2.7", ["vina_1.2.7_win.exe", "vina_1.2.7_linux_x86_64", "vina_1.2.7_linux_aarch64",
                          "vina_1.2.7_mac_x86_64", "vina_1.2.7_mac_aarch64",
                          "vina_split_1.2.7_win.exe"]),
    _release("v1.2.3", ["vina_1.2.3_windows_x86_64.exe", "vina_1.2.3_linux_x86_64", "vina_1.2.3_mac_x86_64"]),
    _release("v1.2.2", ["vina_1.2.2_linux_x86_64", "vina_1.2.2_macos_x86_64", "vina_1.2.2_macos_arm64"]),
    _release("v1.1.2-boost-new", ["vina_1.1.2-boost-new_linux_x86_64"]),
]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.setattr(vm.requests, "get", lambda *a, **k: _FakeResponse(_FAKE_RELEASES_JSON))
    return vm.VinaReleaseManager(cache_dir=tmp_path / "vina_cache")


def test_list_remote_assets_mengabaikan_vina_split(manager):
    assets = manager.list_remote_assets()
    assert all("split" not in a.filename for a in assets)


def test_klasifikasi_windows_1_2_7(manager):
    assets = manager.list_remote_assets()
    win = [a for a in assets if a.version == "1.2.7" and a.os_name == "windows"]
    assert len(win) == 1
    assert win[0].arch == "x86_64"


def test_v1_2_2_tidak_ada_windows(manager):
    assets = manager.list_remote_assets()
    v122_windows = [a for a in assets if a.version == "1.2.2" and a.os_name == "windows"]
    assert v122_windows == []  # 1.2.0-1.2.2 memang tidak menyediakan build Windows


def test_v1_2_3_windows_terklasifikasi_one_off_naming(manager):
    assets = manager.list_remote_assets()
    win = [a for a in assets if a.version == "1.2.3" and a.os_name == "windows"]
    assert len(win) == 1
    assert win[0].filename == "vina_1.2.3_windows_x86_64.exe"


def test_legacy_boost_new_linux_only(manager):
    assets = manager.list_remote_assets()
    legacy = [a for a in assets if "1.1.2" in a.version]
    assert len(legacy) == 1
    assert legacy[0].os_name == "linux"


def test_list_compatible_filter_by_host(manager, monkeypatch):
    monkeypatch.setattr(vm, "_host_os", lambda: "linux")
    monkeypatch.setattr(vm, "_host_arch", lambda: "x86_64")
    compatible = manager.list_compatible()
    assert all(a.os_name == "linux" and a.arch == "x86_64" for a in compatible)
    versions = {a.version for a in compatible}
    assert "1.2.7" in versions
    assert "1.2.2" in versions  # linux tersedia di semua era


def test_list_compatible_windows_tidak_termasuk_1_2_2(manager, monkeypatch):
    monkeypatch.setattr(vm, "_host_os", lambda: "windows")
    monkeypatch.setattr(vm, "_host_arch", lambda: "x86_64")
    compatible = manager.list_compatible()
    versions = {a.version for a in compatible}
    assert "1.2.2" not in versions
    assert "1.2.7" in versions
    assert "1.2.3" in versions


def test_resolve_raise_jika_tak_ada_kompatibel(manager, monkeypatch):
    monkeypatch.setattr(vm.requests, "get", lambda *a, **k: _FakeResponse([]))
    with pytest.raises(RuntimeError):
        manager.resolve()


def test_version_key_toleran_suffix_non_numerik():
    assert vm.VinaReleaseManager._version_key("1.1.2-boost-new") == (1, 1, 2)
    assert vm.VinaReleaseManager._version_key("1.2.0.dev3") == (1, 2, 0, 3)


def test_find_cached_urutan_numerik_bukan_string(manager, tmp_path):
    cache_dir = manager._cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    for name in ("vina_1.2.2_windows_x86_64.exe", "vina_1.2.10_windows_x86_64.exe", "vina_1.2.9_windows_x86_64.exe"):
        (cache_dir / name).write_bytes(b"dummy")

    found = manager._find_cached(None)
    assert found.name == "vina_1.2.10_windows_x86_64.exe"


def test_find_cached_versi_spesifik(manager):
    cache_dir = manager._cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    for name in ("vina_1.2.5_windows_x86_64.exe", "vina_1.2.7_windows_x86_64.exe"):
        (cache_dir / name).write_bytes(b"dummy")

    assert manager._find_cached("1.2.5").name == "vina_1.2.5_windows_x86_64.exe"
    assert manager._find_cached("1.2.9") is None


def test_resolve_pakai_cache_tanpa_panggil_network(manager, monkeypatch):
    cache_dir = manager._cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "vina_1.2.5_windows_x86_64.exe").write_bytes(b"dummy")

    def fail_if_called(*a, **k):
        raise AssertionError("Tidak boleh memanggil network ketika versi sudah ada di cache")

    monkeypatch.setattr(vm.requests, "get", fail_if_called)
    result = manager.resolve(version="1.2.5")
    assert result.name == "vina_1.2.5_windows_x86_64.exe"


def test_resolve_fallback_ke_cache_saat_network_gagal_versi_tak_ditentukan(manager, monkeypatch):
    cache_dir = manager._cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "vina_1.2.5_windows_x86_64.exe").write_bytes(b"dummy")

    def fail_network(*a, **k):
        raise ConnectionError("simulasi network mati")

    monkeypatch.setattr(vm.requests, "get", fail_network)
    result = manager.resolve()  # version=None -> boleh fallback ke cache apa pun
    assert result.name == "vina_1.2.5_windows_x86_64.exe"


def test_resolve_tidak_fallback_diam_diam_jika_versi_spesifik_diminta(manager, monkeypatch):
    def fail_network(*a, **k):
        raise ConnectionError("simulasi network mati")

    monkeypatch.setattr(vm.requests, "get", fail_network)
    with pytest.raises(RuntimeError):
        manager.resolve(version="1.2.5")  # cache kosong, versi spesifik diminta -> harus raise, bukan diam2 pakai versi lain


def test_resolve_vina_executable_tidak_ada_path_lookup():
    from chemflow.docking.vina_runner import resolve_vina_executable
    import inspect

    sig = inspect.signature(resolve_vina_executable)
    assert "prefer_path_env" not in sig.parameters
