"""Test integrasi ekspor interaksi BIOVIA: konfigurasi, tahap pipeline, CLI, dan laporan similaritas."""

import json
import logging

import pandas as pd
import pytest
from openpyxl import Workbook

import chemflow.cli as cli
import chemflow.interaction as interaction
from chemflow import Pipeline, PipelineConfig
from chemflow.interaction import BioviaUnavailableError, ExportSummary, InteractionJob
from chemflow.interaction.biovia_gui import BioviaError, BioviaLicenseError
from chemflow.similarity.report import SimilarityReport, run_similarity_report


@pytest.fixture
def inputs(tmp_path):
    ligand = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Etanol"], "smiles": ["CCO"]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)
    return ligand, receptor, tmp_path / "out"


def _config(inputs, **overrides):
    ligand, receptor, out = inputs
    return PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=out, openbabel_path=ligand,
                          show_progress=False, **overrides)


# ---------------------------------------------------------------- konfigurasi

def test_similarity_otomatis_secara_bawaan(inputs):
    cfg = _config(inputs)
    assert cfg.run_similarity is None and cfg.biovia_exe is None and cfg.biovia_launch_timeout == 90.0
    assert cfg.lock_input is True
    assert cfg.interactions_dir == cfg.output_dir / "interaksi"


def test_mode_otomatis_tanpa_native_tidak_error_hanya_dilewati(inputs):
    cfg = _config(inputs, include_native=False)
    assert cfg.run_similarity is None


def test_similarity_butuh_ligan_native(inputs):
    with pytest.raises(ValueError, match="ligan native"):
        _config(inputs, run_similarity=True, include_native=False)
    _config(inputs, run_similarity=True, include_native=False, run_rmsd_validation=True)


def test_batas_waktu_biovia_harus_positif(inputs):
    with pytest.raises(ValueError, match="biovia_launch_timeout"):
        _config(inputs, biovia_launch_timeout=0)


def test_setelan_biovia_ikut_tersimpan_dan_dipulihkan(inputs, tmp_path):
    exe = tmp_path / "DiscoveryStudio2021.exe"
    cfg = _config(inputs, run_similarity=True, biovia_exe=exe, biovia_launch_timeout=45)
    restored = PipelineConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
    assert restored.run_similarity is True and restored.biovia_exe == exe.resolve()
    assert restored.biovia_launch_timeout == 45


# ------------------------------------------------------------ tahap pipeline

class _Recorder:
    def __init__(self, summary=None, error=None):
        self.summary, self.error, self.export_args, self.report_args = summary, error, None, None

    def export(self, output_dir, interactions_dir, **kwargs):
        self.export_args = (output_dir, interactions_dir, kwargs)
        if self.error:
            raise self.error
        return self.summary or ExportSummary()

    def report(self, output_dir, **kwargs):
        self.report_args = (output_dir, kwargs)
        return SimilarityReport(results=[], workbook=None)


def _patch(monkeypatch, recorder):
    monkeypatch.setattr(interaction, "export_interactions", recorder.export)
    monkeypatch.setattr("chemflow.similarity.report.run_similarity_report", recorder.report)


def test_tahap_meneruskan_setelan_lalu_menghitung_similaritas(inputs, monkeypatch, tmp_path):
    exe = tmp_path / "DiscoveryStudio2021.exe"
    pipeline = Pipeline(_config(inputs, run_similarity=True, biovia_exe=exe, biovia_launch_timeout=30,
                                figure_dpi=150, plot_max_rows=10))
    job = InteractionJob("1AKI_R001", tmp_path / "gagal_complex.pdb", tmp_path)
    recorder = _Recorder(summary=ExportSummary(failed=[(job, "boom")]))
    _patch(monkeypatch, recorder)

    pipeline._run_interactions_and_similarity()

    output_dir, interactions_dir, kwargs = recorder.export_args
    assert output_dir == pipeline.cfg.output_dir and interactions_dir == pipeline.cfg.interactions_dir
    assert kwargs["executable"] == exe.resolve() and kwargs["launch_timeout"] == 30
    assert pipeline.failed_interactions == ["1AKI_R001/gagal_complex"]
    assert recorder.report_args[1]["dpi"] == 150 and recorder.report_args[1]["max_rows"] == 10


@pytest.mark.parametrize("error", [
    BioviaUnavailableError("BIOVIA tidak ditemukan"), BioviaLicenseError("lisensi ditolak"),
    BioviaError("fokus hilang"), FileNotFoundError("complexes/ tidak ada"),
])
def test_biovia_tak_bisa_dipakai_tidak_menggagalkan_run_dan_similaritas_tetap_dihitung(inputs, monkeypatch, caplog, error):
    pipeline = Pipeline(_config(inputs, run_similarity=True))
    recorder = _Recorder(error=error)
    _patch(monkeypatch, recorder)

    pipeline.log.propagate = True
    with caplog.at_level(logging.ERROR, logger="chemflow"):
        pipeline._run_interactions_and_similarity()

    assert str(error) in caplog.text and "berkas interaksi yang sudah ada" in caplog.text
    assert recorder.report_args is not None                    # analisis tetap jalan dari berkas yang ada


def _plan(monkeypatch, executable):
    monkeypatch.setattr(interaction, "detect_biovia", lambda explicit=None: executable)


def test_otomatis_aktif_bila_biovia_terdeteksi(inputs, monkeypatch, tmp_path):
    _plan(monkeypatch, tmp_path / "DiscoveryStudio2021.exe")
    assert Pipeline(_config(inputs))._similarity_enabled() is True


def test_otomatis_dilewati_bila_biovia_tidak_terdeteksi(inputs, monkeypatch, caplog):
    _plan(monkeypatch, None)
    pipeline = Pipeline(_config(inputs))
    pipeline.log.propagate = True
    with caplog.at_level(logging.INFO, logger="chemflow"):
        assert pipeline._similarity_enabled() is False
    assert "BIOVIA tidak terdeteksi" in caplog.text


def test_otomatis_dilewati_tanpa_native(inputs, monkeypatch, tmp_path):
    _plan(monkeypatch, tmp_path / "DiscoveryStudio2021.exe")
    assert Pipeline(_config(inputs, include_native=False))._similarity_enabled() is False


def test_no_similarity_mematikan_walau_biovia_ada(inputs, monkeypatch, tmp_path):
    _plan(monkeypatch, tmp_path / "DiscoveryStudio2021.exe")
    assert Pipeline(_config(inputs, run_similarity=False))._similarity_enabled() is False


def test_similarity_paksa_tidak_menunggu_deteksi(inputs, monkeypatch):
    _plan(monkeypatch, None)
    assert Pipeline(_config(inputs, run_similarity=True))._similarity_enabled() is True


def test_ctrl_c_saat_ekspor_diteruskan_agar_run_bisa_dilanjutkan(inputs, monkeypatch):
    pipeline = Pipeline(_config(inputs, run_similarity=True))
    _patch(monkeypatch, _Recorder(error=KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        pipeline._run_interactions_and_similarity()


# ----------------------------------------------------------------------- CLI

def test_parser_run_opsi_similarity():
    base = ["run", "--ligands", "a.xlsx", "--receptors", "b.xlsx"]
    args = cli.build_parser().parse_args(base)
    assert args.similarity is None and args.biovia_exe is None and args.biovia_timeout == 90.0
    assert args.no_lock_input is False
    args = cli.build_parser().parse_args(base + ["--similarity", "--biovia-exe", "D.exe", "--biovia-timeout", "30",
                                                 "--no-lock-input"])
    assert args.similarity is True and str(args.biovia_exe) == "D.exe" and args.biovia_timeout == 30.0
    assert args.no_lock_input is True
    assert cli.build_parser().parse_args(base + ["--no-similarity"]).similarity is False


def test_run_meneruskan_opsi_similarity_ke_config(inputs, monkeypatch):
    ligand, receptor, out = inputs
    captured = {}

    class FakePipeline:
        def __init__(self, config, resume=False):
            captured["config"] = config

        def run(self):
            return 0

    monkeypatch.setattr(cli, "Pipeline", FakePipeline)
    code = cli.main(["run", "--ligands", str(ligand), "--receptors", str(receptor), "--output", str(out),
                     "--openbabel-path", str(ligand), "--similarity", "--biovia-timeout", "12"])
    assert code == 0
    assert captured["config"].run_similarity is True and captured["config"].biovia_launch_timeout == 12.0
    assert captured["config"].lock_input is True


def test_parser_interactions_default_dan_opsi():
    args = cli.build_parser().parse_args(["interactions", "--output", "hasil"])
    assert (args.command, args.force, args.receptor, args.interaction_suffix) == ("interactions", False, None, "_interaksi.xlsx")
    args = cli.build_parser().parse_args(["interactions", "--output", "hasil", "--force", "--receptor", "1UWH_R001",
                                          "--interaction-suffix", "_nb.xlsx", "--biovia-exe", "D.exe"])
    assert args.force is True and args.receptor == "1UWH_R001" and str(args.biovia_exe) == "D.exe"


def test_parser_interactions_butuh_output():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["interactions"])


def test_parser_resume_bisa_ganti_path_biovia():
    args = cli.build_parser().parse_args(["resume", "--output", "hasil", "--biovia-exe", "D.exe"])
    assert str(args.biovia_exe) == "D.exe"


def _job(tmp_path, name):
    return InteractionJob("1AAA_R001", tmp_path / f"{name}_complex.pdb", tmp_path)


def test_interactions_kode_keluar_dan_ringkasan(monkeypatch, tmp_path, capsys):
    calls = {}

    def fake_export(output, interactions_dir, **kwargs):
        calls.update(output=output, kwargs=kwargs)
        return ExportSummary(succeeded=[_job(tmp_path, "a")], failed=[], skipped=2)

    monkeypatch.setattr(interaction, "export_interactions", fake_export)
    assert cli.main(["interactions", "--output", str(tmp_path), "--force", "--receptor", "R1", "--no-progress"]) == 0
    assert calls["kwargs"]["force"] is True and calls["kwargs"]["receptor"] == "R1"
    assert calls["kwargs"]["show_progress"] is False
    assert "1 kompleks berhasil, 0 gagal, 2 dilewati" in capsys.readouterr().out


def test_interactions_ada_yang_gagal_kode_1(monkeypatch, tmp_path, capsys):
    summary = ExportSummary(failed=[(_job(tmp_path, "b"), "tab tidak ditemukan")])
    monkeypatch.setattr(interaction, "export_interactions", lambda *a, **k: summary)
    assert cli.main(["interactions", "--output", str(tmp_path)]) == 1
    assert "1AAA_R001/b_complex: tab tidak ditemukan" in capsys.readouterr().out


@pytest.mark.parametrize("error, code", [
    (BioviaUnavailableError("BIOVIA tidak ditemukan"), 1), (FileNotFoundError("complexes/"), 1),
    (BioviaLicenseError("lisensi"), 1), (KeyboardInterrupt(), 130),
])
def test_interactions_galat_dipetakan_ke_kode_keluar(monkeypatch, tmp_path, error, code):
    def boom(*args, **kwargs):
        raise error

    monkeypatch.setattr(interaction, "export_interactions", boom)
    assert cli.main(["interactions", "--output", str(tmp_path)]) == code


# ---------------------------------------------------------- laporan similaritas

def _biovia_excel(path, contacts, chain="X", resname="LIG"):
    wb = Workbook()
    ws = wb.active
    for i, (num, name, kind) in enumerate(contacts):
        source, target = f"A:{name}{num}:OG", f"{chain}:{resname}1:C{i}"
        ws.append([f"{source} - {target}", "Yes", "0 255 0", "Ligand Non-bond Monitor", 1, "Hydrogen Bond", kind,
                   source, "H-Donor", target, "H-Acceptor"])
    wb.save(path)


def _tree(root):
    folder = root / "complexes" / "1AAA_R001"
    folder.mkdir(parents=True)
    for name, native in (("NATIVE_LIG_X1", True), ("alfa", False)):
        pdb = folder / f"{name}_complex.pdb"
        pdb.write_text("REMARK\n")
        pdb.with_suffix(".json").write_text(json.dumps({
            "ligand_name": name, "ligand_code": "", "ligand_chain": "X", "ligand_resname": "LIG", "is_native": native}))
    interactions = root / "interaksi" / "1AAA_R001"
    interactions.mkdir(parents=True)
    _biovia_excel(interactions / "NATIVE_LIG_X1_complex_interaksi.xlsx",
                  [(75, "HIS", "Conventional Hydrogen Bond"), (102, "VAL", "Van der Waals")])
    _biovia_excel(interactions / "alfa_complex_interaksi.xlsx", [(75, "HIS", "Conventional Hydrogen Bond")])
    return root


def test_laporan_similaritas_menulis_excel_dan_grafik(tmp_path):
    report = run_similarity_report(_tree(tmp_path))
    assert len(report.results) == 1 and report.results[0].aa_similarity_pct == 50.0
    assert report.workbook == tmp_path / "similaritas_interaksi.xlsx" and report.workbook.is_file()
    assert report.plots and all(p.is_file() for p in report.plots)


def test_laporan_similaritas_tanpa_grafik_dan_nama_kustom(tmp_path):
    report = run_similarity_report(_tree(tmp_path), result_filename="hasil.xlsx", make_plots=False)
    assert report.workbook == tmp_path / "hasil.xlsx" and report.plots == []


def test_laporan_similaritas_tanpa_pasangan_tidak_menulis_berkas(tmp_path):
    (tmp_path / "complexes" / "1AAA_R001").mkdir(parents=True)
    report = run_similarity_report(tmp_path)
    assert report.results == [] and report.workbook is None
    assert not (tmp_path / "similaritas_interaksi.xlsx").exists()


def test_laporan_similaritas_tanpa_folder_kompleks_raise(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_similarity_report(tmp_path)
