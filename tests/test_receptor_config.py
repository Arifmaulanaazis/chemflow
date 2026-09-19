"""Test penyusun Excel reseptor interaktif: parsing masukan, ukuran kotak, penulisan Excel, dan alur penuh."""

from pathlib import Path

import pytest

from chemflow.io import receptor_config as rc
from chemflow.io.excel_receptors import read_receptors
from chemflow.io.pdb_fetcher import FetchedReceptor, NativeLigand


def _hetatm(serial: int, atom: str, resname: str, chain: str, resnum: int, x: float, y: float, z: float) -> str:
    return (f"HETATM{serial:>5} {atom:<4} {resname:>3} {chain}{resnum:>4}    "
            f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00           C\n")


def _ligand(resname: str, chain: str, resnum: int, origin: float, length: float, atoms: int = 4) -> NativeLigand:
    step = length / (atoms - 1) if atoms > 1 else 0.0
    lines = [_hetatm(i + 1, f"C{i + 1}", resname, chain, resnum, origin + i * step, 1.0, 2.0) for i in range(atoms)]
    xs = [origin + i * step for i in range(atoms)]
    return NativeLigand(
        chain=chain, resname=resname, resnum=resnum, atom_lines=lines,
        center_x=round(sum(xs) / atoms, 3), center_y=1.0, center_z=2.0,
    )


def _fetcher(ligands_by_code):
    def fetch(code, dest_dir):
        if code not in ligands_by_code:
            raise RuntimeError(f"Gagal mengunduh PDB {code}: tidak ditemukan")
        return FetchedReceptor(pdb_code=code, pdb_path=Path(dest_dir) / f"{code}.pdb",
                               native_ligands=ligands_by_code[code])
    return fetch


def _scripted(answers):
    iterator = iter(answers)
    log = []

    def ask(prompt):
        log.append(prompt)
        return next(iterator)

    return ask, log


def test_native_ligand_extent_mengambil_sisi_terpanjang():
    ligand = _ligand("ABC", "A", 1, origin=0.0, length=12.0)
    assert ligand.extent == pytest.approx(12.0)


def test_native_ligand_extent_tanpa_atom():
    assert NativeLigand(chain="A", resname="ABC", resnum=1).extent == 0.0


@pytest.mark.parametrize("length, expected", [(0.0, 18.0), (6.0, 18.0), (12.0, 20.0), (16.5, 25.0), (40.0, 30.0)])
def test_suggest_box_size(length, expected):
    assert rc.suggest_box_size(_ligand("ABC", "A", 1, 0.0, length)) == expected


def test_parse_pdb_codes_uppercase_dan_tanpa_duplikat():
    assert rc.parse_pdb_codes("6lu7, 3ptb  6LU7;1AKI") == (["6LU7", "3PTB", "1AKI"], [])


def test_parse_pdb_codes_menandai_token_tidak_valid():
    valid, invalid = rc.parse_pdb_codes("6LU7 ABCD 12 x")
    assert valid == ["6LU7"]
    assert invalid == ["ABCD", "12", "x"]


def test_parse_ligand_choice():
    assert rc.parse_ligand_choice("M", 3) == "m"
    assert rc.parse_ligand_choice(" s ", 3) == "s"
    assert rc.parse_ligand_choice("1 3, 1", 3) == [1, 3]
    assert rc.parse_ligand_choice("4", 3) is None
    assert rc.parse_ligand_choice("0", 3) is None
    assert rc.parse_ligand_choice("a", 3) is None
    assert rc.parse_ligand_choice("", 3) is None
    assert rc.parse_ligand_choice("1", 0) is None


def test_parse_box_size():
    assert rc.parse_box_size("", 24.0) == (24.0, 24.0, 24.0)
    assert rc.parse_box_size("22,5", 24.0) == (22.5, 22.5, 22.5)
    assert rc.parse_box_size("20 22 24", 24.0) == (20.0, 22.0, 24.0)
    assert rc.parse_box_size("20 22", 24.0) is None
    assert rc.parse_box_size("abc", 24.0) is None
    assert rc.parse_box_size("0", 24.0) is None
    assert rc.parse_box_size("-5", 24.0) is None
    assert rc.parse_box_size("nan", 24.0) is None


def test_write_receptor_config_terbaca_pipeline(tmp_path):
    rows = [
        rc.ReceptorConfigRow("6LU7", (-10.5, 12.25, 68.0), (24.0, 24.0, 24.0), "N3_A101"),
        rc.ReceptorConfigRow("6LU7", (1.0, 2.0, 3.0), (18.0, 20.0, 22.0), "manual"),
    ]
    path = rc.write_receptor_config(rows, tmp_path / "hasil" / "reseptor.xlsx")
    assert path.exists()

    entries = read_receptors(path)
    assert [e.pdb_code for e in entries] == ["6LU7", "6LU7"]
    assert entries[0].unique_key != entries[1].unique_key
    assert (entries[0].center_x, entries[0].center_y, entries[0].center_z) == (-10.5, 12.25, 68.0)
    assert (entries[1].size_x, entries[1].size_y, entries[1].size_z) == (18.0, 20.0, 22.0)
    assert all(e.has_gridbox_center for e in entries)


def test_alur_penuh_satu_ligan_ukuran_usulan(tmp_path):
    out = tmp_path / "reseptor.xlsx"
    ligands = {"6LU7": [_ligand("N3", "A", 101, 0.0, 12.0)]}
    ask, _ = _scripted(["6lu7", "1", "", str(out)])
    said = []

    assert rc.run_receptor_config(ask, said.append, _fetcher(ligands)) == 0

    entries = read_receptors(out)
    assert len(entries) == 1
    assert entries[0].pdb_code == "6LU7"
    assert (entries[0].center_x, entries[0].center_y, entries[0].center_z) == (6.0, 1.0, 2.0)
    assert (entries[0].size_x, entries[0].size_y, entries[0].size_z) == (20.0, 20.0, 20.0)
    assert any("Tersimpan" in line for line in said)


def test_alur_beberapa_pdb_multi_situs_dan_lewati(tmp_path):
    out = tmp_path / "config.xlsx"
    ligands = {
        "3PTB": [_ligand("BEN", "A", 1, 0.0, 6.0), _ligand("CA", "A", 2, 30.0, 0.0, atoms=1)],
        "1AKI": [_ligand("NAG", "A", 5, 0.0, 10.0)],
        "9XYZ": [],
    }
    ask, _ = _scripted([
        "3PTB 1AKI 9XYZ",
        "1 2", "", "25",
        "s",
        "s",
        str(out),
    ])
    assert rc.run_receptor_config(ask, lambda _: None, _fetcher(ligands)) == 0

    entries = read_receptors(out)
    assert [e.pdb_code for e in entries] == ["3PTB", "3PTB"]
    assert (entries[0].size_x, entries[1].size_x) == (18.0, 25.0)


def test_alur_koordinat_manual_tanpa_ligan_native(tmp_path):
    out = tmp_path / "manual.xlsx"
    ask, _ = _scripted(["9XYZ", "m", "1,5", "abc", "2", "3", "", str(out)])
    assert rc.run_receptor_config(ask, lambda _: None, _fetcher({"9XYZ": []})) == 0

    entry = read_receptors(out)[0]
    assert (entry.center_x, entry.center_y, entry.center_z) == (1.5, 2.0, 3.0)
    assert (entry.size_x, entry.size_y, entry.size_z) == (20.0, 20.0, 20.0)


def test_alur_kode_tidak_valid_diminta_ulang(tmp_path):
    out = tmp_path / "r.xlsx"
    ask, _ = _scripted(["ZZ", "", "6LU7", "1", "", str(out)])
    said = []
    ligands = {"6LU7": [_ligand("N3", "A", 101, 0.0, 12.0)]}

    assert rc.run_receptor_config(ask, said.append, _fetcher(ligands)) == 0
    assert any("Kode tidak valid" in line for line in said)
    assert any("minimal satu kode" in line for line in said)


def test_alur_pilihan_tidak_valid_diminta_ulang(tmp_path):
    out = tmp_path / "r.xlsx"
    ask, _ = _scripted(["6LU7", "7", "x", "1", "not-a-size", "20 20", "21", str(out)])
    said = []
    ligands = {"6LU7": [_ligand("N3", "A", 101, 0.0, 12.0)]}

    assert rc.run_receptor_config(ask, said.append, _fetcher(ligands)) == 0
    assert said.count("Masukan tidak valid.") == 2
    assert read_receptors(out)[0].size_x == 21.0


def test_alur_semua_dilewati_tidak_menulis_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ask, _ = _scripted(["6LU7", "s"])
    ligands = {"6LU7": [_ligand("N3", "A", 101, 0.0, 12.0)]}

    assert rc.run_receptor_config(ask, lambda _: None, _fetcher(ligands)) == 1
    assert not list(tmp_path.glob("*.xlsx"))


def test_alur_unduhan_gagal_dilewati(tmp_path):
    out = tmp_path / "r.xlsx"
    ask, _ = _scripted(["0000 6LU7", "1", "", str(out)])
    said = []
    ligands = {"6LU7": [_ligand("N3", "A", 101, 0.0, 12.0)]}

    assert rc.run_receptor_config(ask, said.append, _fetcher(ligands)) == 0
    assert any("Reseptor 0000 dilewati" in line for line in said)
    assert [e.pdb_code for e in read_receptors(out)] == ["6LU7"]


def test_nama_file_tanpa_ekstensi_dan_tolak_timpa(tmp_path):
    existing = tmp_path / "ada.xlsx"
    existing.write_bytes(b"lama")
    ligands = {"6LU7": [_ligand("N3", "A", 101, 0.0, 12.0)]}
    target = tmp_path / "baru"
    ask, _ = _scripted(["6LU7", "1", "", str(existing.with_suffix("")), "n", str(target)])

    assert rc.run_receptor_config(ask, lambda _: None, _fetcher(ligands)) == 0
    assert existing.read_bytes() == b"lama"
    assert (tmp_path / "baru.xlsx").exists()


def test_nama_file_default_ditulis_di_direktori_kerja(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ligands = {"6LU7": [_ligand("N3", "A", 101, 0.0, 12.0)]}
    ask, _ = _scripted(["6LU7", "1", "", ""])

    assert rc.run_receptor_config(ask, lambda _: None, _fetcher(ligands)) == 0
    assert (tmp_path / rc.DEFAULT_FILENAME).exists()
