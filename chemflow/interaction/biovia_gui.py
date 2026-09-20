"""
Otomasi GUI BIOVIA Discovery Studio (Visualizer atau Client) lewat Windows UI Automation.

Perhitungan interaksi tetap dikerjakan BIOVIA. Modul ini hanya membuka PDB,
memilih ligan, menekan tombol yang sama dengan pengguna, menyimpan diagram 2D,
dan menyalin tabel Non-bond. Kontrol dicari lewat pohon UI (nama, tipe, kelas),
bukan koordinat layar, sehingga tahan terhadap perubahan ukuran jendela dan DPI.

Selama ekspor mouse dan keyboard dipakai aplikasi: pengguna tidak boleh
menyentuhnya. Sebelum mengirim tombol atau klik, fokus jendela BIOVIA diperiksa
agar input tidak bocor ke aplikasi lain. Tiap kompleks dibuka dari salinan
sementara bernama unik (``<basis>_cf<kode>``), sehingga tab dan diagramnya tidak
pernah bentrok dengan dokumen milik pengguna yang senama. Hanya dokumen chemflow
sendiri yang ditutup (tanpa menyimpan); dokumen pengguna tidak disentuh.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from chemflow.interaction.biovia_install import BioviaLocator, BioviaUnavailableError
from chemflow.interaction.input_lock import InputLock
from chemflow.interaction.table import DEFAULT_HEADERS, NonbondTable

_PROCESS_RE = re.compile(r"^DiscoveryStudio(\d{4})?\.exe$", re.IGNORECASE)
_DIALOG_TITLES = ("Close Window", "Close all windows", "BIOVIA Discovery Studio")
_MAIN_TITLE = "Discovery Studio"
_WM_CLOSE = 0x0010
_SW_RESTORE, _SW_MAXIMIZE = 9, 3


class BioviaError(RuntimeError):
    """Kegagalan mengendalikan BIOVIA (kontrol tidak ditemukan, fokus hilang, waktu habis)."""


class BioviaLicenseError(BioviaError):
    """BIOVIA menolak lisensi saat dibuka."""


class _Runtime:
    """Dependensi khusus Windows, dimuat hanya saat otomasi benar-benar dipakai."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise BioviaUnavailableError("Otomasi BIOVIA hanya tersedia di Windows.")
        try:
            import psutil
            import pyperclip
            import win32gui
            import win32process
            from PIL import ImageGrab
            from pywinauto import Application, mouse
            from pywinauto.keyboard import send_keys
        except ImportError as exc:
            raise BioviaUnavailableError(
                "Dependensi otomasi Windows belum lengkap. Pasang dengan: pip install pywinauto pyperclip psutil"
            ) from exc
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()   # koordinat UIA dan tangkapan layar harus satu skala
        except Exception:
            pass
        self.psutil, self.pyperclip = psutil, pyperclip
        self.win32gui, self.win32process = win32gui, win32process
        self.ImageGrab, self.Application, self.mouse, self.send_keys = ImageGrab, Application, mouse, send_keys


class BioviaClient:
    """Backend ``InteractionBackend`` yang mengendalikan jendela BIOVIA."""

    def __init__(self, executable: Optional[Path] = None, launch_timeout: float = 90.0,
                 locator: Optional[BioviaLocator] = None, logger: Optional[logging.Logger] = None,
                 input_lock: Optional[InputLock] = None) -> None:
        self._log = logger or logging.getLogger(__name__)
        self._lock = input_lock or InputLock(enabled=False)
        self._rt = _Runtime()
        self._locator = locator or BioviaLocator()
        self._explicit = executable
        self._launch_timeout = launch_timeout
        self._pid: Optional[int] = None
        self._created: Optional[float] = None
        self._launched_here = False
        self._hwnd: Optional[int] = None
        self._window: Any = None
        self._opened: Dict[str, Tuple[str, Path]] = {}   # basis -> (nama tab unik, folder salinan)
        self._last_dialog = ""

    # ------------------------------------------------------------------ sesi

    def is_alive(self) -> bool:
        if self._pid is None:
            return False
        try:
            process = self._rt.psutil.Process(self._pid)
            return process.is_running() and process.create_time() == self._created
        except self._rt.psutil.Error:
            return False

    def prepare(self) -> None:
        """Hubungkan BIOVIA (dibuka bila belum jalan) dan siapkan jendelanya."""
        if not self.is_alive():
            self._connect()
        self._show_maximized()
        self._focus()

    def close(self) -> None:
        """Tutup BIOVIA bila dijalankan oleh chemflow; instance milik pengguna dibiarkan."""
        if not (self._launched_here and self.is_alive()):
            self._discard_copies()
            return
        try:
            self._rt.win32gui.PostMessage(self._hwnd, _WM_CLOSE, 0, 0)
            self._dismiss_prompts(timeout=3.0)
            deadline = time.monotonic() + 10
            while self.is_alive() and time.monotonic() < deadline:
                time.sleep(0.3)
            if self.is_alive():
                self._rt.psutil.Process(self._pid).kill()
        except Exception:
            self._log.debug("Penutupan BIOVIA tidak bersih.", exc_info=True)
        self._discard_copies()

    def _discard_copies(self) -> None:
        for _, folder in self._opened.values():
            shutil.rmtree(folder, ignore_errors=True)
        self._opened.clear()

    def recover(self) -> None:
        """Bersihkan dialog dan tab yang dibuka chemflow setelah satu kompleks gagal."""
        try:
            self._focus()
            self._dismiss_prompts(timeout=1.5)
        except Exception:
            self._log.debug("Pemulihan dialog BIOVIA belum berhasil.", exc_info=True)
        for stem in list(self._opened):
            try:
                self.close_complex(stem)
            except Exception:
                self._log.debug(f"Tab '{stem}' belum bisa ditutup.", exc_info=True)

    def _find_pid(self) -> Optional[int]:
        for process in self._rt.psutil.process_iter(["pid", "name"]):
            try:
                if _PROCESS_RE.match(process.info.get("name") or ""):
                    return process.info["pid"]
            except self._rt.psutil.Error:
                continue
        return None

    def _top_windows(self) -> List[Tuple[int, str, str]]:
        """Jendela tingkat atas milik BIOVIA yang terlihat: (handle, judul, kelas).

        Memakai win32gui alih-alih ``window_text()`` pywinauto, yang bisa menggantung
        selamanya bila jendela lain milik BIOVIA sedang sibuk.
        """
        found: List[Tuple[int, str, str]] = []
        gui, proc = self._rt.win32gui, self._rt.win32process

        def collect(hwnd: int, _: Any) -> bool:
            if gui.IsWindowVisible(hwnd) and proc.GetWindowThreadProcessId(hwnd)[1] == self._pid:
                found.append((hwnd, gui.GetWindowText(hwnd), gui.GetClassName(hwnd)))
            return True

        gui.EnumWindows(collect, None)
        return found

    def _connect(self) -> None:
        pid = self._find_pid()
        self._launched_here = False
        if pid is None:
            executable = self._locator.find_executable(self._explicit)
            if executable is None:
                raise BioviaUnavailableError(
                    "BIOVIA Discovery Studio tidak ditemukan. Pasang aplikasinya atau berikan --biovia-exe."
                )
            self._log.info(f"Menjalankan BIOVIA: {executable}")
            pid = self._locator.launch(executable).pid
            self._launched_here = True
        else:
            self._log.info("Memakai BIOVIA yang sudah berjalan.")

        deadline = time.monotonic() + self._launch_timeout
        main = None
        while time.monotonic() < deadline:
            self._lock.pulse()
            self._pid = pid
            if not self._rt.psutil.pid_exists(pid):
                pid = self._find_pid() or pid    # instance lama mengambil alih peluncuran
            windows = self._top_windows()
            for hwnd, title, _ in windows:
                if title == "BIOVIA Discovery Studio" and self._launched_here:
                    self._raise_if_license_error(hwnd)
            main = next((w for w in windows if w[1].startswith(_MAIN_TITLE) and w[2].startswith("Qt")), None)
            if main is not None:
                break
            time.sleep(0.5)
        if main is None:
            raise TimeoutError(f"Jendela BIOVIA tidak muncul dalam {self._launch_timeout:g} detik.")

        self._hwnd = main[0]
        self._created = self._rt.psutil.Process(self._pid).create_time()
        app = self._rt.Application(backend="uia").connect(handle=self._hwnd)
        self._window = app.window(handle=self._hwnd)

    def _raise_if_license_error(self, hwnd: int) -> None:
        """Dialog galat lisensi: ambil teksnya, tutup BIOVIA yang gagal, lalu laporkan."""
        message, detail = "", ""
        try:
            dialog = self._rt.Application(backend="uia").connect(handle=hwnd).window(handle=hwnd)
            message = " ".join(c.window_text() for c in dialog.descendants(control_type="Text")
                               if c.element_info.automation_id.endswith("m_messageCtrl"))
            more = dialog.child_window(title="More", control_type="Button")
            if more.exists(timeout=0.5):
                more.invoke()
                time.sleep(0.5)
                detail = " ".join(c.window_text() for c in dialog.descendants(control_type="Text")
                                  if c.element_info.automation_id.endswith("m_detailedMessageCtrl"))
        except Exception:
            self._log.debug("Teks dialog BIOVIA tidak terbaca.", exc_info=True)
        if "licens" not in (message + detail).lower():
            return
        try:
            self._rt.psutil.Process(self._pid).kill()
        except self._rt.psutil.Error:
            pass
        raise BioviaLicenseError(
            f"BIOVIA menolak lisensi saat dibuka: {message} {detail}".strip()
            + " Periksa lisensi lewat Start Menu > BIOVIA > Licensing, atau buka BIOVIA manual sebelum menjalankan chemflow."
        )

    def _show_maximized(self) -> None:
        gui = self._rt.win32gui
        if gui.IsIconic(self._hwnd):
            gui.ShowWindow(self._hwnd, _SW_RESTORE)
        if gui.GetWindowPlacement(self._hwnd)[1] != _SW_MAXIMIZE:
            gui.ShowWindow(self._hwnd, _SW_MAXIMIZE)
            time.sleep(0.8)

    def _focus(self) -> None:
        try:
            self._window.set_focus()
        except Exception:
            self._log.debug("set_focus gagal.", exc_info=True)

    def _ensure_foreground(self) -> None:
        """Pastikan jendela aktif milik BIOVIA sebelum mengirim input; input tidak boleh bocor ke aplikasi lain."""
        for attempt in range(3):
            foreground = self._rt.win32gui.GetForegroundWindow()
            if foreground and self._rt.win32process.GetWindowThreadProcessId(foreground)[1] == self._pid:
                return
            self._focus()
            time.sleep(0.4)
        raise BioviaError("Fokus jendela BIOVIA hilang. Jangan memakai mouse atau keyboard selama ekspor berjalan.")

    def _keys(self, keys: str) -> None:
        self._lock.pulse()
        self._ensure_foreground()
        self._rt.send_keys(keys)

    def _click(self, control: Any) -> None:
        self._lock.pulse()
        self._ensure_foreground()
        control.click_input()

    def _click_point(self, x: int, y: int) -> None:
        self._lock.pulse()
        self._ensure_foreground()
        self._rt.mouse.click(button="left", coords=(x, y))

    # ------------------------------------------------------------- pencarian

    def _wait(self, condition: Callable[[], Any], timeout: float, what: str, poll: float = 0.3) -> Any:
        deadline = time.monotonic() + timeout
        while True:
            self._lock.pulse()
            value = condition()
            if value:
                return value
            if time.monotonic() >= deadline:
                raise BioviaError(f"Waktu habis menunggu: {what}.")
            time.sleep(poll)

    def _control(self, **criteria: Any) -> Optional[Any]:
        """Kontrol pertama yang cocok, atau ``None`` bila tidak ada."""
        try:
            spec = self._window.child_window(**criteria)
            return spec.wrapper_object() if spec.exists(timeout=0.2) else None
        except Exception:
            return None

    def _checkbox(self, title: str) -> Any:
        control = self._control(title=title, control_type="CheckBox")
        if control is None:
            raise BioviaError(f"Kontrol '{title}' tidak ditemukan di BIOVIA.")
        return control

    def _switch_on(self, title: str, timeout: float = 30.0) -> None:
        """Nyalakan tombol toggle (dilewati bila sudah menyala), menunggu sampai bisa diklik."""
        def enabled() -> Optional[Any]:
            control = self._control(title=title, control_type="CheckBox")
            return control if control is not None and control.is_enabled() else None

        control = self._wait(enabled, timeout, f"tombol '{title}' aktif")
        try:
            already = control.get_toggle_state() == 1
        except Exception:
            already = False
        if not already:
            try:
                control.invoke()
            except Exception:
                self._click(control)

    # --------------------------------------------------------------- dialog

    def _dialogs(self) -> List[Tuple[int, str, str]]:
        return [w for w in self._top_windows() if w[0] != self._hwnd and w[1] != ""]

    def _dismiss_prompts(self, timeout: float = 3.0, choice: str = "No") -> bool:
        """Jawab dialog konfirmasi BIOVIA (default ``No``, tanpa menyimpan) sampai tenang."""
        deadline = time.monotonic() + timeout
        handled, quiet_since = False, None
        while time.monotonic() < deadline:
            acted = False
            for hwnd, title, klass in self._dialogs():
                if title not in _DIALOG_TITLES:
                    continue
                try:
                    dialog = self._rt.Application(backend="uia").connect(handle=hwnd).window(handle=hwnd)
                    text = " ".join(c.window_text() for c in dialog.descendants(control_type="Text")).strip()
                    button = dialog.child_window(title=choice, control_type="Button")
                    if not button.exists(timeout=0.1):
                        button = dialog.child_window(title="OK", control_type="Button")
                        if not button.exists(timeout=0.1):
                            continue
                        self._log.warning(f"Dialog BIOVIA ditutup: {text}")
                    self._last_dialog = text
                    button.wrapper_object().invoke()
                except Exception:
                    continue
                time.sleep(0.5)
                handled = acted = True
                quiet_since = None
                break
            if acted:
                continue
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since > 0.8:
                break
            time.sleep(0.2)
        return handled

    # ------------------------------------------------------- dokumen dan tab

    def _tab(self, predicate: Callable[[str], bool]) -> Optional[Any]:
        """Tab dokumen di bagian atas jendela yang namanya memenuhi ``predicate``."""
        window_top = self._window.rectangle().top
        try:
            tabs = self._window.descendants(control_type="TabItem")
        except Exception:
            return None
        for tab in tabs:
            try:
                rect = tab.rectangle()
                if 0 <= rect.top - window_top < 130 and rect.right > rect.left and predicate(tab.window_text()):
                    return tab
            except Exception:
                continue
        return None

    def _close_tabs(self, predicate: Callable[[str], bool], attempts: int = 6) -> None:
        for _ in range(attempts):
            tab = self._tab(predicate)
            if tab is None:
                return
            self._click(tab)
            time.sleep(0.3)
            self._keys("^w")
            time.sleep(0.5)
            self._dismiss_prompts(timeout=2.0)
        raise BioviaError("Tab BIOVIA tidak mau tertutup; periksa dialog yang terbuka.")

    def close_complex(self, stem: str) -> None:
        """Tutup diagram 2D lalu dokumen kompleks tanpa menyimpan perubahannya."""
        alias, folder = self._opened.get(stem, (stem, None))
        self._close_tabs(lambda name: name.startswith(f"{alias}-Ligand "))
        self._close_tabs(lambda name: name == alias)
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        self._opened.pop(stem, None)

    def open_complex(self, path: Path, ligand_chain: Optional[str] = None,
                     ligand_resname: Optional[str] = None) -> str:
        """Buka PDB, pilih ligan (menurut rantai dan nama residu bila diberikan), kembalikan labelnya.

        BIOVIA membuka salinan sementara bernama unik. Dua dokumen senama diberi
        akhiran ``(1)`` oleh BIOVIA, dan tab milik pengguna bisa tertukar dengan tab chemflow.
        """
        path = Path(path).resolve()
        alias = f"{path.stem}_cf{uuid.uuid4().hex[:6]}"
        folder = Path(tempfile.mkdtemp(prefix="chemflow_biovia_"))
        copy = folder / f"{alias}.pdb"
        shutil.copyfile(path, copy)
        self._opened[path.stem] = (alias, folder)
        self._focus()
        self._keys("{ESC}")
        self._keys("^o")
        dialog = self._wait(
            lambda: next((w for w in self._dialogs() if w[1] == "Open" and w[2] == "#32770"), None),
            10, "dialog Open")
        box = self._rt.Application(backend="uia").connect(handle=dialog[0]).window(handle=dialog[0])
        box.child_window(title="File name:", control_type="ComboBox").child_window(
            control_type="Edit").set_edit_text(str(copy))
        time.sleep(0.3)
        self._keys("{ENTER}")
        self._wait(lambda: not any(w[2] == "#32770" for w in self._dialogs()), 20, "dialog Open menutup")
        try:
            self._wait(lambda: self._tab(lambda name: name == alias), 90, f"dokumen '{path.stem}' terbuka")
        except BioviaError:
            self._dismiss_prompts(timeout=2.0, choice="OK")
            raise BioviaError(f"BIOVIA tidak dapat membuka {path.name}. {self._last_dialog}".strip())
        self._dismiss_prompts(timeout=1.5)
        self._ensure_tool_panel()
        return self._select_ligand(ligand_chain, ligand_resname)

    def _ensure_tool_panel(self, timeout: float = 30.0) -> None:
        """Panel Receptor-Ligand Interactions harus aktif agar tombol Ligand Interactions muncul."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            button = self._control(title="Ligand Interactions", control_type="CheckBox")
            if button is not None and button.is_visible():
                return
            ribbon = self._control(title="Receptor-Ligand Interactions", control_type="CheckBox")
            if ribbon is not None:
                self._click(ribbon)
                time.sleep(1.0)
            time.sleep(0.4)
        raise BioviaError("Panel Receptor-Ligand Interactions tidak aktif.")

    # ------------------------------------------------------------------ ligan

    def _ligand_label(self) -> Optional[str]:
        control = self._control(title_re=r"Define Ligand.*", control_type="CheckBox")
        return control.window_text() if control is not None else None

    @staticmethod
    def _is_defined(label: Optional[str]) -> bool:
        return bool(label) and "<undefined>" not in label

    def _defined_label(self) -> Optional[str]:
        label = self._ligand_label()
        return label if self._is_defined(label) else None

    def _steppers(self) -> List[Any]:
        """Empat tombol langkah ligan (pertama, sebelumnya, berikutnya, terakhir), kiri ke kanan."""
        boxes = self._window.descendants(control_type="CheckBox")
        anchor = next((c for c in boxes if c.window_text().startswith("Define Ligand")), None)
        if anchor is None:
            raise BioviaError("Label 'Define Ligand' tidak ditemukan.")
        bottom = anchor.rectangle().bottom
        row = [c for c in boxes if not c.window_text() and 0 <= c.rectangle().top - bottom < 60]
        row.sort(key=lambda c: c.rectangle().left)
        if len(row) != 4:
            raise BioviaError(f"Tombol langkah ligan tidak lengkap ({len(row)} dari 4).")
        return row

    @staticmethod
    def _label_matches(label: str, chain: Optional[str], resname: Optional[str]) -> bool:
        """Label BIOVIA berbentuk ``<dokumen>:<rantai>(<resname><nomor>)``, mis. ``x_complex:X(E201)``.

        Nama residu boleh berakhir angka (``E20`` + nomor ``1``), jadi dicocokkan
        dengan nilai yang diharapkan, bukan dipisah dengan pola umum.
        """
        pattern = (
            r":" + (re.escape(chain) if chain else r"[^:()\s]+")
            + r"\(" + (f"(?i:{re.escape(resname)})" if resname else r"[A-Za-z0-9]+?") + r"-?\d+\)\s*$"
        )
        return re.search(pattern, label) is not None

    def _select_ligand(self, chain: Optional[str], resname: Optional[str]) -> str:
        """Langkahi daftar ligan sampai ligan yang diminta terpilih (tanpa target: ligan terakhir)."""
        first, _previous, following, last = self._steppers()
        if not (chain or resname):
            self._click(last)
            return self._wait(self._defined_label, 10, "ligan terpilih")
        self._click(first)
        label = self._wait(self._defined_label, 10, "ligan pertama terdefinisi")
        for _ in range(60):
            if self._label_matches(label, chain, resname):
                return label
            self._click(following)
            time.sleep(0.8)
            updated = self._defined_label()
            if updated is None or updated == label:
                break
            label = updated
        raise BioviaError(f"Ligan {chain or ''}:{resname or ''} tidak ada di daftar ligan BIOVIA.")

    # ----------------------------------------------------------------- diagram

    def export_diagram(self, path: Path) -> None:
        """Hitung interaksi, tampilkan diagram 2D, dan simpan tangkapan panelnya sebagai PNG."""
        self._switch_on("Ligand Interactions")
        self._close_tabs(lambda name: any(name.startswith(f"{alias}-Ligand ") for alias, _ in self._opened.values()))
        self._switch_on("Show 2D Diagram", timeout=60.0)
        widget = self._wait(lambda: self._control(class_name="BindingSiteDepiction::Widget2dBase"),
                            30, "diagram 2D")
        time.sleep(1.2)   # beri waktu render gambar dan legenda
        self._focus()
        rect = widget.rectangle()
        legend = self._control(class_name="BindingSiteDepiction::LegendWidget")
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        if legend is not None:
            lr = legend.rectangle()
            left, top, right, bottom = min(left, lr.left), min(top, lr.top), max(right, lr.right), max(bottom, lr.bottom)
        self._ensure_foreground()
        self._rt.mouse.move(coords=(self._window.rectangle().left + 5, self._window.rectangle().top - 12))
        time.sleep(0.3)   # tooltip dari klik sebelumnya hilang
        image = self._rt.ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        low, high = image.convert("L").getextrema()
        if low == high:
            raise BioviaError("Tangkapan diagram 2D kosong; pastikan jendela BIOVIA terlihat penuh.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG")

    # ---------------------------------------------------------------- tabel

    def _table(self) -> Optional[Any]:
        return self._control(class_name="Table::TableView")

    def _table_headers(self, table: Any) -> Tuple[str, ...]:
        """Judul kolom yang tampil (kolom tersembunyi punya persegi panjang nol), kiri ke kanan."""
        found = []
        for header in table.descendants(control_type="Header"):
            rect = header.rectangle()
            if rect.width() > 0 and rect.height() > 0:
                found.append((rect.top, rect.left, header.window_text()))
        if not found:
            return DEFAULT_HEADERS
        row_top = min(top for top, _, _ in found)
        return tuple(text for top, _, text in sorted((h for h in found if h[0] == row_top), key=lambda h: h[1]))

    def _expand_results(self) -> None:
        """Buka panel hasil di dasar tampilan 3D bila tabelnya belum terlihat."""
        if self._table() is not None:
            return
        for _ in range(2):
            handles = [h for h in self._window.descendants(control_type="Thumb")
                       if h.element_info.class_name == "Acf::ViewSplitterHandle"
                       and h.rectangle().width() > 300 and h.rectangle().height() < 20]
            if not handles:
                raise BioviaError("Pemisah panel hasil tidak ditemukan; periksa tata letak BIOVIA.")
            rect = max(handles, key=lambda h: h.rectangle().top).rectangle()
            self._click_point((rect.left + rect.right) // 2, rect.top + 4)
            time.sleep(1.0)
            if self._table() is not None:
                return
        raise BioviaError("Panel hasil BIOVIA tidak terbuka.")

    def _select_nonbond_tab(self) -> bool:
        """Pilih tab Non-bond, menggeser deretan tab bila tersembunyi. ``False`` bila tabnya tidak ada."""
        for _ in range(20):
            tab = self._control(title="Non-bond", control_type="TabItem")
            if tab is None:
                return False
            rect = tab.rectangle()
            if rect.width() > 0 and rect.height() > 0:
                self._click(tab)
                time.sleep(0.8)
                table = self._table()
                if table is not None and "Category" in self._table_headers(table):
                    return True
            scroll = self._control(title="Scroll Right", control_type="Button")
            if scroll is None:
                return False
            self._click(scroll)
            time.sleep(0.2)
        return False

    def read_nonbond(self) -> NonbondTable:
        """Baca tabel Non-bond lewat clipboard; tabel tanpa interaksi memberi teks kosong."""
        self._expand_results()
        if not self._select_nonbond_tab():
            self._log.warning("BIOVIA tidak menampilkan tab Non-bond (kompleks tanpa interaksi); dicatat tanpa baris.")
            return NonbondTable(DEFAULT_HEADERS, "")
        table = self._table()
        headers = self._table_headers(table)
        cells: List[Any] = []
        for _ in range(4):
            cells = [c for c in table.descendants(control_type="DataItem")
                     if c.rectangle().width() > 0 and c.rectangle().height() > 0]
            if cells:
                break
            time.sleep(0.5)
        if not cells:
            return NonbondTable(headers, "")
        return NonbondTable(headers, self._copy_table(cells))

    def _copy_table(self, cells: List[Any], timeout: float = 3.0) -> str:
        """Pilih semua baris dan salin. Penanda unik mencegah isi clipboard lama dianggap hasil."""
        clipboard = self._rt.pyperclip
        try:
            previous = clipboard.paste()
        except Exception:
            previous = ""
        marker = f"__CHEMFLOW_{time.time_ns()}__"
        try:
            clipboard.copy(marker)
            first = min(cells, key=lambda c: (c.rectangle().top, c.rectangle().left)).rectangle()
            self._click_point((first.left + first.right) // 2, (first.top + first.bottom) // 2)
            time.sleep(0.3)
            self._keys("^a")
            time.sleep(0.3)
            self._keys("^c")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                text = clipboard.paste()
                if text != marker and text.strip():
                    return text
                time.sleep(0.1)
            raise BioviaError("Penyalinan tabel Non-bond gagal: clipboard tidak berisi data baru.")
        finally:
            try:
                clipboard.copy(previous)
            except Exception:
                pass
