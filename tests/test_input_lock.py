"""Test logika kunci input (tanpa memasang hook sungguhan)."""

import pytest

from chemflow.interaction import InputLock, InputLockAborted

INJECTED_KEY, INJECTED_MOUSE = 0x10, 0x01
ESC, KEYDOWN = 0x1B, 0x0100


def test_input_hasil_suntikan_lolos_dan_input_fisik_dibuang():
    lock = InputLock(enabled=False)
    assert lock.should_block("keyboard", INJECTED_KEY, 0x41, KEYDOWN) is False
    assert lock.should_block("mouse", INJECTED_MOUSE) is False
    assert lock.should_block("keyboard", 0, 0x41, KEYDOWN) is True
    assert lock.should_block("mouse", 0) is True
    assert (lock.passed, lock.blocked) == (2, 2)


def test_flag_suntikan_dibedakan_menurut_jenis_perangkat():
    lock = InputLock(enabled=False)
    assert lock.should_block("keyboard", INJECTED_MOUSE, 0x41, KEYDOWN) is True    # 0x01 bukan flag suntikan keyboard
    assert lock.should_block("mouse", INJECTED_KEY) is True                          # 0x10 bukan flag suntikan mouse


def test_esc_tiga_kali_beruntun_membatalkan():
    lock = InputLock(enabled=False)
    for moment in (10.0, 10.5, 11.0):
        assert lock.should_block("keyboard", 0, ESC, KEYDOWN, now=moment) is True
    with pytest.raises(InputLockAborted):
        lock.pulse()


def test_esc_terlalu_lambat_atau_hasil_suntikan_tidak_membatalkan():
    lock = InputLock(enabled=False)
    for moment in (10.0, 12.5, 15.0):
        lock.should_block("keyboard", 0, ESC, KEYDOWN, now=moment)
    for moment in (20.0, 20.1, 20.2):
        lock.should_block("keyboard", INJECTED_KEY, ESC, KEYDOWN, now=moment)       # Esc dari otomasi tidak dihitung
    lock.pulse()


def test_pembatalan_pengguna_adalah_keyboard_interrupt():
    assert issubclass(InputLockAborted, KeyboardInterrupt)


def test_kunci_nonaktif_tidak_memasang_apa_pun():
    lock = InputLock(enabled=False)
    with lock:
        assert lock.active is False
    lock.pulse()


def test_tidak_aktif_di_platform_selain_windows(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    lock = InputLock(enabled=True)
    assert lock.enabled is False
    with lock:
        assert lock.active is False
