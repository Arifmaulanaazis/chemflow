"""Test logika pengendali GUI BIOVIA dengan runtime dan kontrol tiruan (tanpa Windows atau BIOVIA)."""

import sys
from types import SimpleNamespace

import pytest

from chemflow.interaction import biovia_gui
from chemflow.interaction.biovia_gui import BioviaClient, BioviaError
from chemflow.interaction.biovia_install import BioviaUnavailableError


class FakeClipboard:
    def __init__(self, on_copy_keys=None, initial="teks pengguna"):
        self.value = initial
        self.on_copy_keys = on_copy_keys      # dipanggil saat Ctrl+C dikirim
        self.history = []

    def copy(self, text):
        self.history.append(text)
        self.value = text

    def paste(self):
        return self.value


class FakeRuntime(SimpleNamespace):
    pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(biovia_gui.time, "sleep", lambda _: None)
    clipboard = FakeClipboard()
    sent = []

    def send_keys(keys):
        sent.append(keys)
        if keys == "^c" and clipboard.on_copy_keys:
            clipboard.value = clipboard.on_copy_keys()

    runtime = FakeRuntime(pyperclip=clipboard, send_keys=send_keys, mouse=SimpleNamespace(click=lambda **k: None),
                          win32gui=SimpleNamespace(GetForegroundWindow=lambda: 1),
                          win32process=SimpleNamespace(GetWindowThreadProcessId=lambda h: (0, 42)))
    monkeypatch.setattr(biovia_gui, "_Runtime", lambda: runtime)
    instance = BioviaClient()
    instance._pid = 42
    instance._window = SimpleNamespace(set_focus=lambda: None)
    instance.sent, instance.clipboard = sent, clipboard
    return instance


def test_bukan_windows_ditolak_dengan_pesan_jelas(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(BioviaUnavailableError, match="hanya tersedia di Windows"):
        BioviaClient()


@pytest.mark.parametrize("label, chain, resname, expected", [
    ("Define Ligand: k_complex:X(ASP1)", "X", "ASP", True),
    ("Define Ligand: k_complex:X(ASP1)", "X", "asp", True),                 # nama residu tak peka huruf
    ("Define Ligand: k_complex:X(ASP1)", "X", "GLU", False),
    ("Define Ligand: k_complex:A(MG401)", "X", "MG", False),                # rantai berbeda
    ("Define Ligand: k_complex:X(E201)", "X", "E20", True),                 # nama residu berakhir angka
    ("Define Ligand: k_complex:X(ASP1)", None, "ASP", True),
    ("Define Ligand: k_complex:X(ASP1)", "X", None, True),
    ("Define Ligand: k_complex:X(ASP1)", "XY", "ASP", False),
    ("Define Ligand: <undefined>", "X", "ASP", False),
])
def test_label_ligan_dicocokkan_dengan_rantai_dan_residu(label, chain, resname, expected):
    assert BioviaClient._label_matches(label, chain, resname) is expected


def _scripted_ligands(client, labels):
    """Tombol next menggeser ke label berikutnya; label terakhir bertahan bila next ditekan lagi."""
    state = {"i": None, "clicks": []}
    buttons = {name: object() for name in ("first", "previous", "next", "last")}
    client._steppers = lambda: [buttons[n] for n in ("first", "previous", "next", "last")]

    def click(control):
        name = next(n for n, b in buttons.items() if b is control)
        state["clicks"].append(name)
        if name == "first":
            state["i"] = 0
        elif name == "next":
            state["i"] = min((state["i"] or 0) + 1, len(labels) - 1)
        elif name == "last":
            state["i"] = len(labels) - 1

    client._click = click
    client._ligand_label = lambda: "Define Ligand: <undefined>" if state["i"] is None else labels[state["i"]]
    return state


def test_pilih_ligan_menurut_rantai_melewati_ligan_lain(client):
    state = _scripted_ligands(client, ["Define Ligand: k:B(CO3)", "Define Ligand: k:X(ASP1)"])
    assert client._select_ligand("X", "ASP") == "Define Ligand: k:X(ASP1)"
    assert state["clicks"] == ["first", "next"]


def test_pilih_ligan_pertama_cocok_tidak_melangkah(client):
    state = _scripted_ligands(client, ["Define Ligand: k:X(ASP1)", "Define Ligand: k:Y(GOL2)"])
    client._select_ligand("X", "ASP")
    assert state["clicks"] == ["first"]


def test_pilih_ligan_tidak_ada_berhenti_di_akhir_daftar(client):
    state = _scripted_ligands(client, ["Define Ligand: k:A(MG1)", "Define Ligand: k:B(CO3)"])
    with pytest.raises(BioviaError, match="X:ASP"):
        client._select_ligand("X", "ASP")
    assert state["clicks"] == ["first", "next", "next"]             # berhenti saat label tidak berubah


def test_tanpa_target_memilih_ligan_terakhir(client):
    state = _scripted_ligands(client, ["Define Ligand: k:A(MG1)", "Define Ligand: k:X(ASP1)"])
    assert client._select_ligand(None, None) == "Define Ligand: k:X(ASP1)"
    assert state["clicks"] == ["last"]


class FakeHeader:
    def __init__(self, text, left, top=816, width=60, height=23):
        self._rect = SimpleNamespace(left=left, top=top, width=lambda: width, height=lambda: height)
        self._text = text

    def rectangle(self):
        return self._rect

    def window_text(self):
        return self._text


class FakeTable:
    def __init__(self, headers):
        self._headers = headers

    def descendants(self, control_type=None):
        return self._headers


def test_judul_kolom_hanya_yang_tampil_urut_kiri_ke_kanan(client):
    table = FakeTable([
        FakeHeader("Distance", 300), FakeHeader("Name", 100), FakeHeader("ID", 0, top=-23, width=0, height=0),   # tersembunyi
        FakeHeader("1", 90, top=839), FakeHeader("Category", 400),                                              # 1 = nomor baris
    ])
    assert client._table_headers(table) == ("Name", "Distance", "Category")


def test_judul_kolom_bawaan_bila_tidak_terbaca(client):
    from chemflow.interaction.table import DEFAULT_HEADERS
    assert client._table_headers(FakeTable([])) == DEFAULT_HEADERS


def _cell(x=10, y=20):
    return SimpleNamespace(rectangle=lambda: SimpleNamespace(left=x, top=y, right=x + 60, bottom=y + 20))


def test_salin_tabel_mengembalikan_teks_dan_memulihkan_clipboard(client):
    client.clipboard.on_copy_keys = lambda: "A\tB\r\n"
    text = client._copy_table([_cell()], timeout=1)
    assert text == "A\tB\r\n"
    assert client.sent == ["^a", "^c"]
    assert client.clipboard.value == "teks pengguna"                    # isi clipboard pengguna dikembalikan
    assert client.clipboard.history[0].startswith("__CHEMFLOW_")


def test_salin_tabel_gagal_bila_clipboard_tidak_berubah(client):
    with pytest.raises(BioviaError, match="clipboard tidak berisi data baru"):
        client._copy_table([_cell()], timeout=0.2)
    assert client.clipboard.value == "teks pengguna"


def test_input_ditolak_bila_fokus_bukan_di_biovia(client):
    client._rt.win32process = SimpleNamespace(GetWindowThreadProcessId=lambda h: (0, 999))   # jendela aktif milik aplikasi lain
    with pytest.raises(BioviaError, match="Fokus jendela BIOVIA hilang"):
        client._keys("^w")
    assert client.sent == []                                            # tidak ada tombol yang bocor


def test_tutup_kompleks_hanya_menyentuh_tab_salinan_chemflow(client, tmp_path):
    """Dokumen pengguna yang senama ('aspirin_complex' atau 'aspirin_complex (1)') tidak boleh tertutup."""
    folder = tmp_path / "salinan"
    folder.mkdir()
    (folder / "x.pdb").write_text("REMARK\n")
    client._opened = {"aspirin_complex": ("aspirin_complex_cfab12", folder)}
    closed = []
    client._close_tabs = closed.append

    client.close_complex("aspirin_complex")

    diagram, document = closed
    assert document("aspirin_complex_cfab12")
    assert not document("aspirin_complex") and not document("aspirin_complex (1)")
    assert diagram("aspirin_complex_cfab12-Ligand 1") and not diagram("aspirin_complex-Ligand 1")
    assert not folder.exists() and client._opened == {}


def test_salinan_sementara_dibersihkan_walau_biovia_tidak_dijalankan_chemflow(client, tmp_path):
    folder = tmp_path / "salinan"
    folder.mkdir()
    client._opened = {"x_complex": ("x_complex_cf000000", folder)}
    client._launched_here = False
    client.close()
    assert not folder.exists() and client._opened == {}
