"""Ligan native sebagai referensi: ukuran gridbox default dari native, redocking, RMSD, analitik, dan prompt interaktif."""

import builtins
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import chemflow.pipeline as pipeline_module
from chemflow.chem.ligand_preparer import LigandPrepResult
from chemflow.config import PipelineConfig
from chemflow.docking.docking_matrix import DockingRunResult, ReceptorDockingTarget
from chemflow.docking.grid_box import GridBox, parse_box_size
from chemflow.io.excel_receptors import ReceptorEntry
from chemflow.io.pdb_fetcher import FetchedReceptor, NativeLigand, interactive_select_native_ligand
from chemflow.pipeline import NativeEntry, Pipeline


def _hetatm(serial, atom, resname, chain, resnum, x, y, z):
    return (f"HETATM{serial:>5} {atom:<4} {resname:>3} {chain}{resnum:>4}    "
            f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00           C\n")


def _native(resname="ABC", chain="A", resnum=1, center=(0.0, 0.0, 0.0), length=12.0):
    """Ligan native lurus sepanjang sumbu x dengan ekstensi ``length`` dan pusat ``center``."""
    atoms = 4
    step = length / (atoms - 1)
    cx, cy, cz = center
    xs = [cx - length / 2 + i * step for i in range(atoms)]
    lines = [_hetatm(i + 1, f"C{i + 1}", resname, chain, resnum, x, cy, cz) for i, x in enumerate(xs)]
    return NativeLigand(chain=chain, resname=resname, resnum=resnum, atom_lines=lines,
                        center_x=cx, center_y=cy, center_z=cz)


@pytest.mark.parametrize("extent, expected", [(None, 18.0), (0.0, 18.0), (10.0, 18.0), (12.0, 20.0),
                                              (15.6, 24.0), (16.5, 25.0), (40.0, 30.0)])
def test_suggested_size_kubus_extent_ditambah_padding(extent, expected):
    assert GridBox.suggested_size(extent) == expected


def test_suggested_size_padding_dan_batas_bisa_diatur():
    assert GridBox.suggested_size(10.0, padding=4.0, min_size=10.0) == 14.0
    assert GridBox.suggested_size(30.0, max_size=35.0) == 35.0


def test_parse_box_size_pindah_ke_grid_box():
    assert parse_box_size("22,5", 20.0) == (22.5, 22.5, 22.5)
    assert parse_box_size("", 24.0) == (24.0, 24.0, 24.0)


def _script(monkeypatch, answers):
    iterator = iter(answers)
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(iterator)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", fake_input)
    return prompts


def _fetched(*ligands):
    return FetchedReceptor(pdb_code="6LU7", pdb_path=Path("6LU7.pdb"), native_ligands=list(ligands))


def test_interaktif_default_ukuran_dari_native_bukan_20(monkeypatch):
    native = _native(length=15.6, center=(5.0, 6.0, 7.0))
    prompts = _script(monkeypatch, ["1", ""])                       # pilih native 1, Enter = terima ukuran
    cx, cy, cz, sx, sy, sz, chosen = interactive_select_native_ligand(_fetched(native))
    assert (cx, cy, cz) == (5.0, 6.0, 7.0) and (sx, sy, sz) == (24.0, 24.0, 24.0) and chosen is native
    assert "24 A" in prompts[-1] and "15.6" in prompts[-1] and "padding 8" in prompts[-1]


def test_interaktif_padding_bisa_diatur(monkeypatch):
    _script(monkeypatch, ["1", "y"])
    *_, sx, sy, sz, _ = interactive_select_native_ligand(_fetched(_native(length=12.0)), padding=4.0)
    assert (sx, sy, sz) == (18.0, 18.0, 18.0)                       # 12 + 4 = 16, minimal 18


def test_interaktif_tolak_ukuran_satu_angka_jadi_kubus(monkeypatch):
    _script(monkeypatch, ["1", "n", "27"])
    *_, sx, sy, sz, _ = interactive_select_native_ligand(_fetched(_native()))
    assert (sx, sy, sz) == (27.0, 27.0, 27.0)


def test_interaktif_tolak_ukuran_tiga_angka_dan_ulangi_bila_salah(monkeypatch):
    _script(monkeypatch, ["1", "n", "abc", "20 22", "20 22 24"])
    *_, sx, sy, sz, _ = interactive_select_native_ligand(_fetched(_native()))
    assert (sx, sy, sz) == (20.0, 22.0, 24.0)


def test_interaktif_tabel_menampilkan_kolom_kotak(monkeypatch, capsys):
    _script(monkeypatch, ["1", ""])
    interactive_select_native_ligand(_fetched(_native(length=12.0)))
    output = capsys.readouterr().out
    assert "Kotak" in output and " 20" in output


def test_interaktif_manual_memakai_ukuran_default_config(monkeypatch):
    _script(monkeypatch, ["m", "1", "2", "3", ""])
    cx, cy, cz, sx, sy, sz, chosen = interactive_select_native_ligand(_fetched(_native()), default_size=(21.0,) * 3)
    assert (cx, cy, cz, sx, sy, sz) == (1.0, 2.0, 3.0, 21.0, 21.0, 21.0) and chosen is None


def test_interaktif_tanpa_native_manual(monkeypatch):
    _script(monkeypatch, ["4", "5", "6", "n", "30"])
    cx, cy, cz, sx, sy, sz, chosen = interactive_select_native_ligand(_fetched())
    assert (cx, cy, cz, sx, sy, sz) == (4.0, 5.0, 6.0, 30.0, 30.0, 30.0) and chosen is None


def test_interaktif_non_tty_ditolak(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(RuntimeError, match="non-TTY"):
        interactive_select_native_ligand(_fetched(_native()))


@pytest.fixture
def make_pipeline(tmp_path):
    ligand = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Etanol"], "smiles": ["CCO"]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)

    def build(**overrides):
        cfg = PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=tmp_path / "out",
                             openbabel_path=ligand, show_progress=False, **overrides)
        return Pipeline(cfg)

    return build


def _entry(**kwargs):
    defaults = dict(pdb_code="6LU7", row_index=1, center_x=0.0, center_y=0.0, center_z=0.0)
    defaults.update(kwargs)
    return ReceptorEntry(**defaults)


def test_gridbox_excel_tanpa_ukuran_memakai_ukuran_native(make_pipeline):
    pipeline = make_pipeline()
    box, native = pipeline._resolve_gridbox(_entry(), _fetched(_native(length=15.6)))
    assert (box.size_x, box.size_y, box.size_z) == (24.0, 24.0, 24.0)
    assert native is not None and box.ref_label == native.label


def test_gridbox_excel_ukuran_eksplisit_menang_dan_sisanya_dari_native(make_pipeline):
    pipeline = make_pipeline()
    box, _ = pipeline._resolve_gridbox(_entry(size_x=30.0), _fetched(_native(length=15.6)))
    assert (box.size_x, box.size_y, box.size_z) == (30.0, 24.0, 24.0)
    box, _ = pipeline._resolve_gridbox(_entry(uniform_size=22.0), _fetched(_native(length=15.6)))
    assert (box.size_x, box.size_y, box.size_z) == (22.0, 22.0, 22.0)


def test_gridbox_padding_dari_config(make_pipeline):
    pipeline = make_pipeline(box_padding=4.0)
    box, _ = pipeline._resolve_gridbox(_entry(), _fetched(_native(length=20.0)))
    assert box.size_x == 24.0


def test_gridbox_tanpa_native_memakai_default_box_size(make_pipeline):
    pipeline = make_pipeline(default_box_size=26.0)
    box, native = pipeline._resolve_gridbox(_entry(), _fetched())
    assert (box.size_x, box.size_y, box.size_z) == (26.0, 26.0, 26.0) and native is None


def test_gridbox_native_jauh_dari_pusat_tidak_dipakai(make_pipeline, caplog):
    pipeline = make_pipeline()
    pipeline.log.propagate = True
    far = _native(center=(30.0, 0.0, 0.0), length=15.6)
    with caplog.at_level("WARNING", logger="chemflow"):
        box, native = pipeline._resolve_gridbox(_entry(), _fetched(far))
    assert native is None and box.size_x == 20.0 and box.ref_label is None
    assert "bukan situs yang sama" in caplog.text


def test_gridbox_batas_jarak_native_bisa_diatur(make_pipeline):
    pipeline = make_pipeline(native_match_radius=40.0)
    _, native = pipeline._resolve_gridbox(_entry(), _fetched(_native(center=(30.0, 0.0, 0.0))))
    assert native is not None


def test_gridbox_memilih_native_terdekat(make_pipeline):
    pipeline = make_pipeline()
    near, other = _native("NEA", center=(1.0, 0.0, 0.0)), _native("OTH", center=(6.0, 0.0, 0.0))
    _, native = pipeline._resolve_gridbox(_entry(), _fetched(other, near))
    assert native is near


def test_gridbox_tanpa_no_native_native_tidak_dikembalikan_tapi_ukuran_tetap_dari_native(make_pipeline):
    pipeline = make_pipeline(include_native=False)
    box, native = pipeline._resolve_gridbox(_entry(), _fetched(_native(length=15.6)))
    assert native is None and box.size_x == 24.0


def test_gridbox_rmsd_validation_memunculkan_native_walau_no_native(make_pipeline):
    pipeline = make_pipeline(include_native=False, run_rmsd_validation=True)
    _, native = pipeline._resolve_gridbox(_entry(), _fetched(_native()))
    assert native is not None


def test_gridbox_interaktif_mengoper_padding(make_pipeline, monkeypatch):
    captured = {}

    def fake_select(fetched, default_size, padding):
        captured.update(default_size=default_size, padding=padding)
        return 1.0, 2.0, 3.0, 24.0, 24.0, 24.0, None

    monkeypatch.setattr(pipeline_module, "interactive_select_native_ligand", fake_select)
    pipeline = make_pipeline(box_padding=6.0, default_box_size=22.0)
    box, _ = pipeline._resolve_gridbox(SimpleNamespace(has_gridbox_center=False, pdb_code="X", unique_key="X_R001"),
                                       _fetched())
    assert captured == {"default_size": (22.0, 22.0, 22.0), "padding": 6.0}
    assert box.center_x == 1.0


class _Preparer:
    def __init__(self):
        self.calls = []

    def prepare(self, name, smiles, output_dir, **kwargs):
        from rdkit import Chem
        self.calls.append((name, smiles))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{name}.pdb").write_text("ATOM\n")
        (output_dir / f"{name}.pdbqt").write_text("ROOT\n")
        return LigandPrepResult(name=name, smiles=smiles, mol=Chem.MolFromSmiles(smiles), image_path=None,
                                pdb_path=output_dir / f"{name}.pdb", pdbqt_path=output_dir / f"{name}.pdbqt",
                                force_field_used="MMFF94", minimized_energy=None)


def _target(key):
    return ReceptorDockingTarget(key=key, pdb_code=key[:4], receptor_pdbqt=Path(f"{key}.pdbqt"),
                                 receptor_clean_pdb=Path(f"{key}_clean.pdb"),
                                 grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))


def _context(*keys, native=None):
    return {key: {"native": native or _native("N3", "A", 1), "grid_box": None, "receptor_pdbqt": None}
            for key in keys}


def test_prepare_natives_menurunkan_smiles_dan_menyiapkan_ligan(make_pipeline, monkeypatch):
    monkeypatch.setattr(pipeline_module, "derive_native_smiles", lambda *a, **k: "CCO")
    pipeline = make_pipeline()
    pipeline._ligand_preparer = _Preparer()
    natives = pipeline._prepare_natives(_context("6LU7_R001"), [_target("6LU7_R001")])
    assert [(n.name, n.label, n.receptor_key, n.smiles) for n in natives] == [
        ("NATIVE_N3_A1", "N3_A1", "6LU7_R001", "CCO")]
    assert natives[0].lipinski["ligand"] == "NATIVE_N3_A1" and natives[0].lipinski["MW"] > 0


def test_prepare_natives_nama_bentrok_antar_reseptor_diberi_akhiran_kunci(make_pipeline, monkeypatch):
    monkeypatch.setattr(pipeline_module, "derive_native_smiles", lambda *a, **k: "CCO")
    pipeline = make_pipeline()
    pipeline._ligand_preparer = _Preparer()
    natives = pipeline._prepare_natives(_context("6LU7_R001", "6Y2E_R002"),
                                        [_target("6LU7_R001"), _target("6Y2E_R002")])
    assert [n.name for n in natives] == ["NATIVE_N3_A1", "NATIVE_N3_A1_6Y2E_R002"]


def test_prepare_natives_gagal_dicatat_dan_tidak_menghentikan_yang_lain(make_pipeline, monkeypatch):
    def derive(block, resname, cache_dir, log):
        if resname == "BAD":
            raise RuntimeError("templat tidak ada")
        return "CCO"

    monkeypatch.setattr(pipeline_module, "derive_native_smiles", derive)
    pipeline = make_pipeline()
    pipeline._ligand_preparer = _Preparer()
    context = {**_context("R1", native=_native("BAD", "A", 1)), **_context("R2", native=_native("OK1", "A", 2))}
    natives = pipeline._prepare_natives(context, [_target("R1"), _target("R2")])
    assert [n.receptor_key for n in natives] == ["R2"]
    assert "templat tidak ada" in pipeline._native_errors["R1"]


def test_prepare_natives_nonaktif_bila_no_native_tanpa_rmsd(make_pipeline):
    pipeline = make_pipeline(include_native=False)
    assert pipeline._prepare_natives(_context("R1"), [_target("R1")]) == []


def test_prepare_natives_resume_memakai_checkpoint_tanpa_menurunkan_smiles_lagi(make_pipeline, monkeypatch):
    monkeypatch.setattr(pipeline_module, "derive_native_smiles", lambda *a, **k: "CCO")
    first = make_pipeline()
    first._ligand_preparer = _Preparer()
    first._prepare_natives(_context("R1"), [_target("R1")])

    def tidak_boleh(*args, **kwargs):
        raise AssertionError("SMILES tidak boleh diturunkan ulang saat resume")

    monkeypatch.setattr(pipeline_module, "derive_native_smiles", tidak_boleh)
    second = make_pipeline()
    second._resume = True
    second._ligand_preparer = _Preparer()
    natives = second._prepare_natives(_context("R1"), [_target("R1")])
    assert natives[0].smiles == "CCO" and second._ligand_preparer.calls == []


class _Orchestrator:
    def __init__(self):
        self.calls = []

    def run_matrix(self, ligand_map, targets, output_dir, **kwargs):
        self.calls.append((dict(ligand_map), [t.key for t in targets], kwargs))
        name = next(iter(ligand_map))
        return [DockingRunResult(ligand_name=name, receptor_key=targets[0].key, replicate=1, seed=1,
                                 poses=[{"mode": 1, "affinity": -9.0}], output_pdbqt=Path("x.pdbqt"))]


def _native_entry(name="NATIVE_N3_A1", key="R1"):
    prep = LigandPrepResult(name=name, smiles="CCO", mol=None, image_path=None, pdb_path=Path("a.pdb"),
                            pdbqt_path=Path("a.pdbqt"), force_field_used="MMFF94", minimized_energy=None)
    return NativeEntry(name=name, label="N3_A1", receptor_key=key, smiles="CCO", prep=prep,
                       lipinski={"ligand": name, "MW": 46.0})


def test_dock_natives_ke_reseptornya_sendiri_dengan_parameter_yang_sama(make_pipeline):
    pipeline = make_pipeline(n_replicates=3, exhaustiveness=16, seed=7)
    pipeline._natives = [_native_entry("NATIVE_A", "R1"), _native_entry("NATIVE_B", "R2")]
    orchestrator = _Orchestrator()
    results = pipeline._dock_natives(orchestrator, [_target("R1"), _target("R2")])

    assert [(list(m), k) for m, k, _ in orchestrator.calls] == [(["NATIVE_A"], ["R1"]), (["NATIVE_B"], ["R2"])]
    kwargs = orchestrator.calls[0][2]
    assert kwargs["n_replicates"] == 3 and kwargs["exhaustiveness"] == 16 and kwargs["base_seed"] == 7
    assert len(results) == 2


def test_dock_natives_kosong(make_pipeline):
    assert make_pipeline()._dock_natives(_Orchestrator(), []) == []


def test_native_properties_hanya_bila_include_native(make_pipeline):
    pipeline = make_pipeline(include_native=False, run_rmsd_validation=True)
    pipeline._natives = [_native_entry()]
    assert pipeline._native_properties() == ([], [])

    pipeline = make_pipeline(run_admet=False)
    pipeline._natives = [_native_entry()]
    lipinski, admet = pipeline._native_properties()
    assert lipinski == [{"ligand": "NATIVE_N3_A1", "MW": 46.0}] and admet == []
    assert pipeline._group_of["NATIVE_N3_A1"] == "Native"


def test_native_admet_disalin_lewat_scraper_dengan_grup_native(make_pipeline, monkeypatch):
    class _Scraper:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, smiles):
            return pd.DataFrame({"raw_smiles": list(smiles), "hERG": [0.3] * len(smiles)})

    monkeypatch.setattr(pipeline_module, "AdmetLabScraper", _Scraper)
    pipeline = make_pipeline()
    pipeline._natives = [_native_entry("NATIVE_A", "R1"), _native_entry("NATIVE_B", "R2")]
    _, admet = pipeline._native_properties()
    assert [(r["ligand"], r["group"], r["hERG"]) for r in admet] == [
        ("NATIVE_A", "Native", 0.3), ("NATIVE_B", "Native", 0.3)]


def test_admet_native_dilewati_pada_mode_file(make_pipeline, tmp_path):
    admet = tmp_path / "admet.csv"
    admet.write_text("smiles,hERG\nCCO,0.1\n")
    pipeline = make_pipeline(admet_file=admet)
    pipeline._natives = [_native_entry()]
    assert pipeline._native_properties()[1] == []


def test_rmsd_validation_membaca_pose_terbaik_hasil_docking_native(make_pipeline, monkeypatch, tmp_path):
    seen = {}

    class _Validator:
        def __init__(self, *args, **kwargs):
            pass

        def validate(self, block, mol, label):
            seen["mol"], seen["label"] = mol, label
            return SimpleNamespace(rmsd=1.4, status="baik", method="stub", note="")

    monkeypatch.setattr(pipeline_module, "RedockingValidator", _Validator)
    monkeypatch.setattr(pipeline_module, "read_pdbqt",
                        lambda path, logger=None: seen.setdefault("paths", []).append(path) or [f"pose:{path.name}"])
    pipeline = make_pipeline(run_rmsd_validation=True)
    pipeline._natives = [_native_entry()]
    results = [
        DockingRunResult(ligand_name="NATIVE_N3_A1", receptor_key="R1", replicate=1, seed=1,
                         poses=[{"mode": 1, "affinity": -8.0}], output_pdbqt=tmp_path / "rep1.pdbqt"),
        DockingRunResult(ligand_name="NATIVE_N3_A1", receptor_key="R1", replicate=2, seed=2,
                         poses=[{"mode": 1, "affinity": -9.5}], output_pdbqt=tmp_path / "rep2.pdbqt"),
    ]
    rows = pipeline._run_rmsd_validation(_context("R1"), results)

    assert seen["paths"] == [tmp_path / "rep2.pdbqt"]              # replikat dengan afinitas terbaik
    assert seen["mol"] == "pose:rep2.pdbqt" and seen["label"] == "N3_A1"
    assert rows == [{"receptor": "R1", "native_ligand": "N3_A1", "rmsd_angstrom": 1.4, "status": "baik",
                     "redock_affinity": -9.5, "metode": "stub", "catatan": ""}]


def test_rmsd_validation_baris_gagal_bila_native_tak_siap_atau_redocking_gagal(make_pipeline):
    pipeline = make_pipeline(run_rmsd_validation=True)
    pipeline._native_errors["R1"] = "templat tidak ada"
    pipeline._natives = [_native_entry("NATIVE_N3_A1_R2", "R2")]
    failed = DockingRunResult(ligand_name="NATIVE_N3_A1_R2", receptor_key="R2", replicate=1, seed=1,
                              error="Vina gagal")
    rows = {r["receptor"]: r for r in pipeline._run_rmsd_validation(_context("R1", "R2"), [failed])}
    assert rows["R1"]["status"] == "gagal" and "templat tidak ada" in rows["R1"]["catatan"]
    assert rows["R2"]["status"] == "gagal" and rows["R2"]["catatan"] == "Vina gagal"


def test_ringkasan_ligan_memuat_native_dengan_tipe(make_pipeline):
    from chemflow.io.excel_ligands import LigandRecord

    pipeline = make_pipeline()
    pipeline._natives = [_native_entry()]
    records = [LigandRecord(name="Etanol", smiles="CCO", group="G1", safe_name="Etanol")]
    rows = pipeline._ligand_summary_rows(records, {"Etanol": object()})
    assert [(r["name"], r["tipe"], r["group"]) for r in rows] == [("Etanol", "uji", "G1"),
                                                                 ("N3_A1", "native", "Native")]
    pipeline = make_pipeline(include_native=False)
    pipeline._natives = [_native_entry()]
    assert len(pipeline._ligand_summary_rows(records, {})) == 1


class _RecordingChartBuilder:
    bar, radar, radar_admet = [], [], []

    def __init__(self, *args, **kwargs):
        pass

    def bar_affinity(self, rows, **kwargs):
        _RecordingChartBuilder.bar.append(kwargs)

    def radar_combined(self, rows, criteria, **kwargs):
        _RecordingChartBuilder.radar.append({"rows": rows, **kwargs})
        return []

    def radar_all_admet_categories(self, rows, **kwargs):
        _RecordingChartBuilder.radar_admet.append(kwargs)
        return []

    def admet_all_stacked_bars(self, *args, **kwargs):
        return []


def test_generate_charts_menyorot_dan_menyematkan_native(make_pipeline, monkeypatch):
    monkeypatch.setattr(pipeline_module, "ChartBuilder", _RecordingChartBuilder)
    _RecordingChartBuilder.bar, _RecordingChartBuilder.radar, _RecordingChartBuilder.radar_admet = [], [], []
    pipeline = make_pipeline()
    stats = [{"ligand": "LigA", "receptor": "R1", "affinity_best": -7.0},
             {"ligand": "NATIVE_X", "receptor": "R1", "affinity_best": -9.0}]
    lipinski = [{"ligand": "LigA", "MW": 180.0, "LogP": 2.0, "HBD": 1, "HBA": 3},
                {"ligand": "NATIVE_X", "MW": 400.0, "LogP": 3.0, "HBD": 2, "HBA": 6}]
    admet = [{"ligand": "LigA", "hERG": 0.2}, {"ligand": "NATIVE_X", "hERG": 0.5}]
    pipeline._generate_charts(stats, lipinski, admet, {"LigA": "G1", "NATIVE_X": "Native"})

    assert _RecordingChartBuilder.bar[0]["highlight_keys"] == {"NATIVE_X"}
    assert _RecordingChartBuilder.radar[0]["pinned"] == {"NATIVE_X"}
    assert _RecordingChartBuilder.radar_admet[0]["pinned"] == {"NATIVE_X"}


def test_generate_charts_tanpa_native_tidak_menyorot(make_pipeline, monkeypatch):
    monkeypatch.setattr(pipeline_module, "ChartBuilder", _RecordingChartBuilder)
    _RecordingChartBuilder.bar = []
    pipeline = make_pipeline()
    pipeline._generate_charts([{"ligand": "LigA", "receptor": "R1", "affinity_best": -7.0}], [], [])
    assert _RecordingChartBuilder.bar[0]["highlight_keys"] == set()


def test_descriptor_matrix_native_masuk_sebagai_grup_sendiri(make_pipeline):
    from chemflow.io.excel_ligands import LigandRecord

    pipeline = make_pipeline()
    records = [LigandRecord(name="Etanol", smiles="CCO", group=None, safe_name="Etanol")]
    lipinski = [{"ligand": "Etanol", "MW": 46.0, "LogP": 0.0, "HBD": 1, "HBA": 1},
                {"ligand": "NATIVE_X", "MW": 400.0, "LogP": 3.0, "HBD": 2, "HBA": 6}]
    _, labels, groups = pipeline._descriptor_matrix(records, lipinski, ["MW", "LogP"],
                                                    {"NATIVE_X": "Native"})
    assert dict(zip(labels, groups)) == {"Etanol": "Tanpa Grup", "NATIVE_X": "Native"}


def test_pca_berjalan_pada_studi_satu_grup_karena_native_jadi_kelompok_kedua(make_pipeline):
    from chemflow.io.excel_ligands import LigandRecord

    pipeline = make_pipeline()
    records = [LigandRecord(name=f"L{i}", smiles="C", group="G1", safe_name=f"L{i}") for i in range(4)]
    lipinski = [{"ligand": f"L{i}", "MW": 100.0 + 10 * i, "LogP": 1.0 + i * 0.3, "HBD": i % 3, "HBA": 2 + i}
                for i in range(4)]
    lipinski.append({"ligand": "NATIVE_X", "MW": 400.0, "LogP": 3.0, "HBD": 2, "HBA": 6})
    pipeline._run_pca(records, lipinski, [], {"NATIVE_X": "Native"})
    assert (pipeline.cfg.analytics_dir / "pca_2d.png").exists()
