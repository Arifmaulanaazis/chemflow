"""
Kunci input fisik (mouse dan keyboard) selama BIOVIA dikendalikan.

Pemasangan hook tingkat rendah membuang setiap peristiwa yang bukan hasil
suntikan program (flag ``injected`` tidak ada), sehingga klik dan ketikan
pengguna tidak sampai ke BIOVIA atau aplikasi lain, sedangkan input yang
dikirim otomasi tetap lewat. Tidak butuh hak administrator.

Pengaman supaya komputer tidak terkunci bila terjadi masalah:
  * Ctrl+Alt+Del tidak bisa dicegat oleh hook, dan hook lenyap bersama prosesnya.
  * Tekan Esc tiga kali berturut-turut (dalam 2 detik) untuk membatalkan; ekspor
    berhenti dengan rapi pada langkah berikutnya.
  * Kunci dilepas otomatis bila otomasi macet lebih dari ``stall_seconds``
    tanpa detak (``pulse``).
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any, List, Optional

_WH_KEYBOARD_LL, _WH_MOUSE_LL = 13, 14
_LLKHF_INJECTED, _LLMHF_INJECTED = 0x10, 0x01
_VK_ESCAPE = 0x1B
_WM_KEYDOWN, _WM_SYSKEYDOWN = 0x0100, 0x0104
_PM_REMOVE = 1
_ESC_PRESSES, _ESC_WINDOW = 3, 2.0


class InputLockAborted(KeyboardInterrupt):
    """Pengguna menekan Esc tiga kali untuk menghentikan otomasi."""


class InputLock:
    """Konteks yang mengunci input fisik selama blok ``with`` berjalan.

    Di platform selain Windows, atau bila hook gagal dipasang, kunci tidak aktif
    dan ``active`` bernilai False; otomasi tetap berjalan dengan penjagaan fokus.
    """

    def __init__(self, enabled: bool = True, stall_seconds: float = 120.0,
                 logger: Optional[logging.Logger] = None) -> None:
        self.enabled = enabled and sys.platform == "win32"
        self.stall_seconds = stall_seconds
        self.active = False
        self.blocked = 0
        self.passed = 0
        self._log = logger or logging.getLogger(__name__)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_pulse = time.monotonic()
        self._aborted = False
        self._escape_times: List[float] = []
        self._callbacks: List[Any] = []

    def __enter__(self) -> "InputLock":
        self.lock()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.unlock()

    def lock(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._stop.clear()
        self._ready.clear()
        self._aborted = False
        self._last_pulse = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="chemflow-input-lock", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)
        if self.active:
            self._log.info("Mouse dan keyboard dikunci selama ekspor BIOVIA. "
                           "Tekan Esc tiga kali berturut-turut untuk membatalkan.")
        else:
            self._log.warning("Mouse dan keyboard tidak bisa dikunci; jangan menyentuhnya selama ekspor BIOVIA.")

    def unlock(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=3.0)
        self.active = False

    def pulse(self) -> None:
        """Tandai otomasi masih bekerja; lempar ``InputLockAborted`` bila pengguna membatalkan."""
        self._last_pulse = time.monotonic()
        if self._aborted:
            self.unlock()
            raise InputLockAborted("Dibatalkan pengguna (Esc tiga kali).")

    def should_block(self, kind: str, flags: int, vk_code: int = 0, message: int = 0, now: Optional[float] = None) -> bool:
        """Putuskan apakah satu peristiwa dibuang. Fungsi murni agar bisa diuji tanpa hook."""
        injected = flags & (_LLKHF_INJECTED if kind == "keyboard" else _LLMHF_INJECTED)
        if injected:
            self.passed += 1
            return False
        self.blocked += 1
        if kind == "keyboard" and vk_code == _VK_ESCAPE and message in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            now = time.monotonic() if now is None else now
            self._escape_times = [t for t in self._escape_times if now - t <= _ESC_WINDOW] + [now]
            if len(self._escape_times) >= _ESC_PRESSES:
                self._aborted = True
                self._stop.set()
        return True

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        lresult = ctypes.c_ssize_t
        proc_type = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = lresult
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, proc_type, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK

        class Keyboard(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class Mouse(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        def on_keyboard(code: int, wparam: int, lparam: int) -> int:
            if code >= 0:
                event = ctypes.cast(lparam, ctypes.POINTER(Keyboard)).contents
                if self.should_block("keyboard", event.flags, event.vkCode, wparam):
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        def on_mouse(code: int, wparam: int, lparam: int) -> int:
            if code >= 0:
                event = ctypes.cast(lparam, ctypes.POINTER(Mouse)).contents
                if self.should_block("mouse", event.flags):
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        self._callbacks = [proc_type(on_keyboard), proc_type(on_mouse)]   # jaga agar tidak dibersihkan GC
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        module = kernel32.GetModuleHandleW(None)
        hooks = [user32.SetWindowsHookExW(_WH_KEYBOARD_LL, self._callbacks[0], module, 0),
                 user32.SetWindowsHookExW(_WH_MOUSE_LL, self._callbacks[1], module, 0)]
        self.active = all(hooks)
        if not self.active:
            self._log.debug(f"Hook input gagal dipasang (kode galat {ctypes.get_last_error() or ctypes.GetLastError()}).")
        self._ready.set()
        message = wintypes.MSG()
        try:
            while self.active and not self._stop.is_set():
                while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, _PM_REMOVE):
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
                if time.monotonic() - self._last_pulse > self.stall_seconds:
                    self._log.warning(f"Otomasi BIOVIA tidak bergerak {self.stall_seconds:g} detik; kunci input dilepas.")
                    break
                time.sleep(0.005)
        finally:
            for hook in hooks:
                if hook:
                    user32.UnhookWindowsHookEx(hook)
            self.active = False
