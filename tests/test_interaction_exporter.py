"""Test pengekspor interaksi BIOVIA dengan backend tiruan (tanpa membuka aplikasinya)."""

import json

import pytest

from chemflow.interaction import InteractionExporter, NonbondTable, discover_jobs, export_interactions
from chemflow.interaction.table import DEFAULT_HEADERS

ROW = ("A:TYR334:OH - X:LIG1:O8\tYes\t0 255 0\tLigand Non-bond Monitor\t2.9\tHydrogen Bond\t"
       "Conventional Hydrogen Bond\tA:TYR334:OH\tH-Donor\tX:LIG1:O8\tH-Acceptor\t110.5\t\t\t\t\t\n")


def _tree(tmp_path, receptors=None):
    """complexes/<kunci>/<basis>.pdb + sidecar; native diberi awalan NATIVE_."""
    receptors = receptors or {"1AAA_R001": ["zeta", "alfa", "NATIVE_LIG_A1"], "2BBB_R002": ["alfa"]}
    for key, names in receptors.items():
        folder = tmp_path / "complexes" / key
        folder.mkdir(parents=True)
        for name in names:
            pdb = folder / f"{name}_complex.pdb"
            pdb.write_text("REMARK\n")
            pdb.with_suffix(".json").write_text(json.dumps({
                "ligand_name": name, "ligand_code": "", "ligand_chain": "X", "ligand_resname": "LIG",
                "is_native": name.startswith("NATIVE_"),
            }))
    return tmp_path


class FakeBackend:
    def __init__(self, table=None, fail_on=(), deaths=0):
        self.calls = []
        self.table = table or NonbondTable(DEFAULT_HEADERS, ROW)
        self.fail_on = set(fail_on)
        self.deaths = deaths      # berapa kali is_alive() melapor proses sudah mati
        self.open = []

    def prepare(self):
        self.calls.append("prepare")

    def is_alive(self):
        if self.deaths > 0:
            self.deaths -= 1
            return False
        return True

    def recover(self):
        self.calls.append("recover")

    def close(self):
        self.calls.append("close")

    def open_complex(self, path, ligand_chain, ligand_resname):
        self.calls.append(("open", path.stem, ligand_chain, ligand_resname))
        if path.stem in self.fail_on:
            raise RuntimeError("BIOVIA gagal membuka")
        self.open.append(path.stem)
        return f"{path.stem}:X(LIG1)"

    def export_diagram(self, path):
        path.write_bytes(b"\x89PNG-tiruan")

    def read_nonbond(self):
        return self.table

    def close_complex(self, stem):
        self.calls.append(("tutup", stem))
        self.open.remove(stem)


def test_discover_jobs_native_lebih_dulu_dan_identitas_dari_sidecar(tmp_path):
    jobs, skipped = discover_jobs(_tree(tmp_path))
    assert skipped == 0
    assert [(j.receptor_key, j.stem) for j in jobs] == [
        ("1AAA_R001", "NATIVE_LIG_A1_complex"), ("1AAA_R001", "alfa_complex"), ("1AAA_R001", "zeta_complex"),
        ("2BBB_R002", "alfa_complex"),
    ]
    assert jobs[0].is_native and not jobs[1].is_native
    assert (jobs[1].ligand_chain, jobs[1].ligand_resname) == ("X", "LIG")


def test_nama_hasil_mengikuti_konvensi_similaritas(tmp_path):
    job = discover_jobs(_tree(tmp_path))[0][0]
    assert job.xlsx_path == tmp_path / "interaksi" / "1AAA_R001" / "NATIVE_LIG_A1_complex_interaksi.xlsx"
    assert job.png_path.name == "NATIVE_LIG_A1_complex_interaksi.png"


def test_discover_jobs_suffix_dan_folder_kustom(tmp_path):
    jobs, _ = discover_jobs(_tree(tmp_path), tmp_path / "lain", xlsx_suffix="_nb.xlsx")
    assert jobs[0].xlsx_path == tmp_path / "lain" / "1AAA_R001" / "NATIVE_LIG_A1_complex_nb.xlsx"
    assert jobs[0].png_path.name == "NATIVE_LIG_A1_complex_nb.png"


def test_discover_jobs_filter_reseptor(tmp_path):
    jobs, _ = discover_jobs(_tree(tmp_path), receptor="2BBB_R002")
    assert [j.receptor_key for j in jobs] == ["2BBB_R002"]


def test_discover_jobs_tanpa_folder_kompleks_raise(tmp_path):
    with pytest.raises(FileNotFoundError, match="chemflow run"):
        discover_jobs(tmp_path)


def test_discover_jobs_tanpa_sidecar_tetap_diantre_dengan_peringatan(tmp_path, caplog):
    root = _tree(tmp_path, {"1AAA_R001": ["alfa"]})
    (root / "complexes" / "1AAA_R001" / "alfa_complex.json").unlink()
    with caplog.at_level("WARNING"):
        jobs, _ = discover_jobs(root)
    assert jobs[0].ligand_chain is None and "Sidecar JSON tidak ada" in caplog.text


def test_hasil_lengkap_dilewati_kecuali_force(tmp_path):
    root = _tree(tmp_path)
    job = discover_jobs(root)[0][0]
    job.output_dir.mkdir(parents=True)
    job.xlsx_path.write_bytes(b"x")
    job.png_path.write_bytes(b"x")
    jobs, skipped = discover_jobs(root)
    assert skipped == 1 and len(jobs) == 3
    jobs, skipped = discover_jobs(root, force=True)
    assert skipped == 0 and len(jobs) == 4


def test_hasil_setengah_atau_kosong_dianggap_belum_selesai(tmp_path):
    root = _tree(tmp_path, {"1AAA_R001": ["alfa"]})
    job = discover_jobs(root)[0][0]
    job.output_dir.mkdir(parents=True)
    job.xlsx_path.write_bytes(b"x")
    job.png_path.write_bytes(b"")
    assert not job.is_complete
    assert len(discover_jobs(root)[0]) == 1


def test_exporter_menulis_png_dan_xlsx_serta_menutup_kompleks(tmp_path):
    root = _tree(tmp_path, {"1AAA_R001": ["alfa"]})
    backend = FakeBackend()
    summary = InteractionExporter(backend, show_progress=False).run(discover_jobs(root)[0])

    assert len(summary.succeeded) == 1 and not summary.failed
    job = summary.succeeded[0]
    assert job.is_complete
    assert ("open", "alfa_complex", "X", "LIG") in backend.calls
    assert backend.calls[0] == "prepare" and backend.calls[-1] == "close"
    assert backend.open == []                                   # dokumen ditutup
    assert not any(p.name.startswith(".biovia-") for p in job.output_dir.iterdir())   # folder sementara bersih


def test_kegagalan_satu_kompleks_tidak_menghentikan_yang_lain(tmp_path):
    root = _tree(tmp_path)
    backend = FakeBackend(fail_on={"zeta_complex"})
    summary = InteractionExporter(backend, show_progress=False).run(discover_jobs(root)[0])

    assert len(summary.succeeded) == 3 and len(summary.failed) == 1
    failed_job, message = summary.failed[0]
    assert failed_job.stem == "zeta_complex" and "gagal membuka" in message
    assert "recover" in backend.calls
    assert not failed_job.xlsx_path.exists() and not failed_job.png_path.exists()   # tidak ada hasil setengah


def test_tabel_kosong_tetap_menghasilkan_berkas_lengkap(tmp_path):
    root = _tree(tmp_path, {"1AAA_R001": ["alfa"]})
    backend = FakeBackend(table=NonbondTable(DEFAULT_HEADERS, ""))
    summary = InteractionExporter(backend, show_progress=False).run(discover_jobs(root)[0])
    assert summary.succeeded[0].is_complete


def test_koneksi_ulang_bila_proses_biovia_terputus(tmp_path):
    root = _tree(tmp_path, {"1AAA_R001": ["alfa"]})
    backend = FakeBackend(deaths=1)
    summary = InteractionExporter(backend, show_progress=False).run(discover_jobs(root)[0])
    assert backend.calls.count("prepare") == 2                  # awal dan sekali lagi karena proses mati
    assert len(summary.succeeded) == 1


def test_antrean_kosong_tidak_menyentuh_backend():
    backend = FakeBackend()
    assert InteractionExporter(backend, show_progress=False).run([]).succeeded == []
    assert backend.calls == []


def test_backend_ditutup_walau_dihentikan_pengguna(tmp_path):
    root = _tree(tmp_path, {"1AAA_R001": ["alfa"]})

    class Interrupted(FakeBackend):
        def export_diagram(self, path):
            raise KeyboardInterrupt

    backend = Interrupted()
    with pytest.raises(KeyboardInterrupt):
        InteractionExporter(backend, show_progress=False).run(discover_jobs(root)[0])
    assert backend.calls[-1] == "close" and ("tutup", "alfa_complex") in backend.calls


def test_export_interactions_melewati_yang_sudah_lengkap_lalu_melanjutkan(tmp_path):
    root = _tree(tmp_path)
    first = export_interactions(root, backend=FakeBackend(fail_on={"zeta_complex"}), show_progress=False)
    assert len(first.succeeded) == 3 and len(first.failed) == 1

    backend = FakeBackend()
    second = export_interactions(root, backend=backend, show_progress=False)
    assert [j.stem for j in second.succeeded] == ["zeta_complex"] and second.skipped == 3

    backend = FakeBackend()
    third = export_interactions(root, backend=backend, show_progress=False)
    assert third.succeeded == [] and third.skipped == 4 and backend.calls == []   # semua lengkap: BIOVIA tidak dibuka
