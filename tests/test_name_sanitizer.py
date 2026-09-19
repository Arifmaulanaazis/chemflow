"""Test sanitize_filename, unique_safe_names, dan derive_pdb_resname."""

import pytest

from chemflow.utils.name_sanitizer import derive_pdb_resname, sanitize_filename, unique_safe_names

_WINDOWS_ILLEGAL = '<>:"/\\|?*'


def test_sanitize_filename_spasi_dan_simbol():
    assert sanitize_filename("Kurkumin (95%)") == "Kurkumin_95"


def test_sanitize_filename_unicode_dinormalisasi():
    result = sanitize_filename("Café Molécule")
    assert result.isascii()
    assert " " not in result


def test_sanitize_filename_kosong_pakai_fallback():
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename(None) == "unnamed"


def test_sanitize_filename_tanpa_huruf_atau_angka_diberi_hash_stabil():
    result = sanitize_filename("###")
    assert result.startswith("unnamed_") and len(result) == len("unnamed_") + 8
    assert result == sanitize_filename("###")
    assert result != sanitize_filename("***")


def test_sanitize_filename_aksara_non_latin_tidak_bentrok():
    a, b = sanitize_filename("阿司匹林"), sanitize_filename("咖啡因")
    assert a != b
    assert a.isascii() and b.isascii()


def test_sanitize_filename_dipotong_max_length():
    long_name = "A" * 200
    result = sanitize_filename(long_name, max_length=10)
    assert len(result) == 10


def test_sanitize_filename_batas_default_menjaga_path_windows():
    assert len(sanitize_filename("x" * 300)) == 60


@pytest.mark.parametrize("char", list(_WINDOWS_ILLEGAL) + ["\t", "\n", "\x00", "\x1f"])
def test_sanitize_filename_membuang_karakter_terlarang_windows(char):
    result = sanitize_filename(f"ab{char}cd")
    assert result == "ab_cd"


def test_sanitize_filename_tanpa_titik_atau_spasi_di_ujung():
    for raw in ("nama.", "nama. ", " nama ", "nama...", ".nama"):
        assert sanitize_filename(raw) == "nama"


@pytest.mark.parametrize("raw", ["CON", "con", "PRN", "Aux", "NUL", "COM1", "com9", "LPT1", "lpt9", "COM²"])
def test_sanitize_filename_nama_perangkat_windows_tidak_lagi_reserved(raw):
    result = sanitize_filename(raw)
    assert result.split(".")[0].upper() not in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM9", "LPT1", "LPT9"}
    assert result.startswith(raw[:3].replace("²", ""))


def test_sanitize_filename_nama_perangkat_dengan_ekstensi():
    assert sanitize_filename("nul.txt") == "nul_.txt"
    assert sanitize_filename("CON.tar.gz") == "CON_.tar.gz"


def test_sanitize_filename_nama_mirip_perangkat_dibiarkan():
    assert sanitize_filename("CONSOLE") == "CONSOLE"
    assert sanitize_filename("COM10") == "COM10"
    assert sanitize_filename("AUX_2") == "AUX_2"


def test_sanitize_filename_huruf_yunani_ditulis_namanya():
    assert sanitize_filename("α-Tocopherol") == "alpha-Tocopherol"
    assert sanitize_filename("β-Carotene") == "beta-Carotene"
    assert sanitize_filename("µ-opioid") == "mu-opioid"
    assert sanitize_filename("ΔG-ligand") == "DeltaG-ligand"


def test_sanitize_filename_huruf_latin_khusus():
    assert sanitize_filename("Straße") == "Strasse"
    assert sanitize_filename("Ørsted") == "Orsted"


def test_sanitize_filename_tidak_diawali_tanda_hubung():
    assert sanitize_filename("-leading-dash") == "leading-dash"
    assert sanitize_filename("(+)-Catechin") == "Catechin"


def test_sanitize_filename_idempoten():
    for raw in ("CON", "nul.txt", "α-Tocopherol", "阿司匹林", "x" * 200, "(+)-Catechin", "a<b>c", "###"):
        once = sanitize_filename(raw)
        assert sanitize_filename(once) == once


def test_unique_safe_names_tanpa_bentrok_tidak_diubah():
    assert unique_safe_names(["Aspirin", "Ibuprofen"]) == ["Aspirin", "Ibuprofen"]


def test_unique_safe_names_bentrok_tanpa_membedakan_huruf_besar_kecil():
    result = unique_safe_names(["Aspirin", "ASPIRIN", "aspirin"])
    assert result == ["Aspirin", "ASPIRIN_2", "aspirin_3"]
    assert len({r.lower() for r in result}) == 3


def test_unique_safe_names_nama_persis_sama():
    assert unique_safe_names(["Kurkumin", "Kurkumin"]) == ["Kurkumin", "Kurkumin_2"]


def test_unique_safe_names_bentrok_setelah_sanitasi():
    result = unique_safe_names(["a/b", "a:b", "a b"])
    assert result == ["a_b", "a_b_2", "a_b_3"]


def test_unique_safe_names_akhiran_tidak_melebihi_max_length():
    long_name = "L" * 100
    result = unique_safe_names([long_name, long_name, long_name], max_length=20)
    assert all(len(r) <= 20 for r in result)
    assert len({r.lower() for r in result}) == 3


def test_unique_safe_names_stabil_terhadap_urutan_untuk_aksara_non_latin():
    assert unique_safe_names(["阿司匹林", "咖啡因"]) == [sanitize_filename("阿司匹林"), sanitize_filename("咖啡因")]


def test_derive_pdb_resname_dari_nama():
    assert derive_pdb_resname("Etanol") == "ETA"
    assert derive_pdb_resname("CoenzymeQ10") == "COE"


def test_derive_pdb_resname_buang_digit_awal():
    assert derive_pdb_resname("123Compound") == "COM"


def test_derive_pdb_resname_hanya_ascii():
    assert derive_pdb_resname("Éthanol") == "ETH"
    assert derive_pdb_resname("α-Tocopherol") == "ALP"
    assert derive_pdb_resname("阿司匹林", "LIG001") == "LIG"


def test_derive_pdb_resname_fallback_ke_kode():
    assert derive_pdb_resname("", "LIG001") == "LIG"


def test_derive_pdb_resname_fallback_akhir():
    assert derive_pdb_resname("", "") == "LIG"
