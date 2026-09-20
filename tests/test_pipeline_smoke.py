"""
Smoke test wiring pipeline: memvalidasi PipelineConfig, struktur direktori
output, dan inisialisasi Pipeline tanpa memanggil tool eksternal (OpenBabel/
Vina/RCSB/ADMETLab3/PubChem), supaya test ini stabil dijalankan di mesin
mana pun tanpa tool tsb terpasang atau koneksi jaringan.

Integrasi penuh dengan binary asli (OpenBabel + AutoDock Vina) bergantung
pada instalasi sistem dan jaringan, sehingga dijalankan lewat CLI, bukan pytest.
"""

from pathlib import Path

import pandas as pd
import pytest

from chemflow.config import PipelineConfig


@pytest.fixture
def sample_excels(tmp_path):
    ligand_df = pd.DataFrame({"name": ["Etanol", "Metanol"], "smiles": ["CCO", "CO"]})
    ligand_path = tmp_path / "ligan.xlsx"
    ligand_df.to_excel(ligand_path, index=False)

    receptor_df = pd.DataFrame({"pdb_code": ["1AKI"], "center_x": [1.0], "center_y": [2.0], "center_z": [3.0]})
    receptor_path = tmp_path / "reseptor.xlsx"
    receptor_df.to_excel(receptor_path, index=False)

    return ligand_path, receptor_path


def test_config_membuat_struktur_direktori(tmp_path, sample_excels):
    ligand_path, receptor_path = sample_excels
    output_dir = tmp_path / "output"

    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, output_dir=output_dir)

    assert cfg.ligand_dir == output_dir / "ligands"
    assert cfg.receptor_dir == output_dir / "receptors"
    assert cfg.docking_dir == output_dir / "docking"
    assert cfg.complex_dir == output_dir / "complexes"
    assert cfg.analytics_dir == output_dir / "analytics"


def test_config_validasi_force_field_invalid(tmp_path, sample_excels):
    ligand_path, receptor_path = sample_excels
    with pytest.raises(ValueError, match="force_field"):
        PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, force_field="INVALID")


def test_config_validasi_n_replicates(tmp_path, sample_excels):
    ligand_path, receptor_path = sample_excels
    with pytest.raises(ValueError, match="n_replicates"):
        PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, n_replicates=0)


def test_config_file_tidak_ada_raise():
    with pytest.raises(FileNotFoundError):
        PipelineConfig(ligand_excel=Path("tidak_ada.xlsx"), receptor_excel=Path("juga_tidak_ada.xlsx"))


def test_config_validasi_merge_mode_invalid(tmp_path, sample_excels):
    ligand_path, receptor_path = sample_excels
    with pytest.raises(ValueError, match="merge_mode"):
        PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, merge_mode="tidak_valid")


def _make_receptor_clean_pdb(path):
    from rdkit import Chem

    mol = Chem.RWMol()
    idx = mol.AddAtom(Chem.Atom("C"))
    info = Chem.AtomPDBResidueInfo()
    info.SetChainId("A")
    info.SetResidueName("ALA")
    info.SetResidueNumber(1)
    info.SetIsHeteroAtom(False)
    info.SetName(" CA ")
    mol.GetAtomWithIdx(idx).SetPDBResidueInfo(info)
    m = mol.GetMol()
    conf = Chem.Conformer(1)
    conf.SetAtomPosition(0, (0.0, 0.0, 0.0))
    m.AddConformer(conf, assignId=True)
    Chem.SanitizeMol(m, catchErrors=True)
    Chem.MolToPDBFile(m, str(path))


def _fake_ligand_mol():
    from rdkit import Chem
    from rdkit.Chem import AllChem

    lig = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(lig, randomSeed=1)
    return lig


def test_merge_poses_best_pilih_afinitas_global_bukan_replikat_1(tmp_path, sample_excels, monkeypatch):
    import chemflow.pipeline as pipeline_module
    from chemflow.docking.docking_matrix import DockingRunResult, ReceptorDockingTarget
    from chemflow.docking.grid_box import GridBox
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path,
                          output_dir=tmp_path / "out", merge_mode="best", openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    receptor_clean = tmp_path / "clean.pdb"
    _make_receptor_clean_pdb(receptor_clean)
    target = ReceptorDockingTarget(key="TEST", pdb_code="TEST", receptor_pdbqt=tmp_path / "dock.pdbqt",
                                    receptor_clean_pdb=receptor_clean,
                                    grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))

    calls = []

    def fake_read_pdbqt(path, logger=None):
        calls.append(path)
        return [_fake_ligand_mol()]

    monkeypatch.setattr(pipeline_module, "read_pdbqt", fake_read_pdbqt)

    rep1_path = tmp_path / "rep1.pdbqt"
    rep2_path = tmp_path / "rep2.pdbqt"
    results = [
        DockingRunResult(ligand_name="LigA", receptor_key="TEST", replicate=1, seed=1,
                          poses=[{"affinity": -5.0}], output_pdbqt=rep1_path),
        DockingRunResult(ligand_name="LigA", receptor_key="TEST", replicate=2, seed=2,
                          poses=[{"affinity": -9.0}], output_pdbqt=rep2_path),
    ]

    pipe._merge_poses(results, [target])

    # Replikat 2 (afinitas -9.0) dipilih karena terbaik secara global, bukan replikat 1.
    assert calls == [rep2_path]
    assert (cfg.complex_dir / "TEST" / "LigA_complex.pdb").exists()


def test_merge_poses_all_merge_semua_replikat_sukses(tmp_path, sample_excels, monkeypatch):
    import chemflow.pipeline as pipeline_module
    from chemflow.docking.docking_matrix import DockingRunResult, ReceptorDockingTarget
    from chemflow.docking.grid_box import GridBox
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path,
                          output_dir=tmp_path / "out", merge_mode="all", openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    receptor_clean = tmp_path / "clean.pdb"
    _make_receptor_clean_pdb(receptor_clean)
    target = ReceptorDockingTarget(key="TEST", pdb_code="TEST", receptor_pdbqt=tmp_path / "dock.pdbqt",
                                    receptor_clean_pdb=receptor_clean,
                                    grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))

    monkeypatch.setattr(pipeline_module, "read_pdbqt", lambda path, logger=None: [_fake_ligand_mol()])

    results = [
        DockingRunResult(ligand_name="LigA", receptor_key="TEST", replicate=1, seed=1,
                          poses=[{"affinity": -5.0}], output_pdbqt=tmp_path / "rep1.pdbqt"),
        DockingRunResult(ligand_name="LigA", receptor_key="TEST", replicate=2, seed=2,
                          poses=[{"affinity": -9.0}], output_pdbqt=tmp_path / "rep2.pdbqt"),
    ]

    pipe._merge_poses(results, [target])

    out_dir = cfg.complex_dir / "TEST"
    assert (out_dir / "LigA_rep01_mode01_complex.pdb").exists()
    assert (out_dir / "LigA_rep02_mode01_complex.pdb").exists()


class _RecordingChartBuilder:
    """Stub ChartBuilder: catat argumen bar_affinity/radar_combined tanpa gambar apa pun."""
    calls = []
    bar_calls = []

    def __init__(self, *args, **kwargs):
        pass

    def bar_affinity(self, rows, **kwargs):
        _RecordingChartBuilder.bar_calls.append({"rows": rows, **kwargs})

    def radar_combined(self, rows, criteria, **kwargs):
        _RecordingChartBuilder.calls.append({"rows": rows, "criteria": criteria, **kwargs})
        return None

    def radar_all_admet_categories(self, *args, **kwargs):
        return []

    def admet_all_stacked_bars(self, *args, **kwargs):
        return []


def test_generate_charts_judul_tanpa_admet_saat_admet_rows_kosong(tmp_path, sample_excels, monkeypatch):
    import chemflow.pipeline as pipeline_module
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path,
                          output_dir=tmp_path / "out", openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    _RecordingChartBuilder.calls = []
    monkeypatch.setattr(pipeline_module, "ChartBuilder", _RecordingChartBuilder)

    replicate_stats = [{"ligand": "LigA", "receptor": "REC1", "affinity_best": -7.0}]
    lipinski_rows = [{"ligand": "LigA", "MW": 180.0, "LogP": 2.0, "HBD": 1, "HBA": 3}]

    pipe._generate_charts(replicate_stats, lipinski_rows, admet_rows=[])

    assert len(_RecordingChartBuilder.calls) == 1
    title = _RecordingChartBuilder.calls[0]["title"]
    assert "ADMET" not in title
    assert title == "Profil Gabungan: Fisikokimia + ΔG"


def test_generate_charts_judul_dengan_admet_saat_admet_rows_ada(tmp_path, sample_excels, monkeypatch):
    import chemflow.pipeline as pipeline_module
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path,
                          output_dir=tmp_path / "out", openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    _RecordingChartBuilder.calls = []
    monkeypatch.setattr(pipeline_module, "ChartBuilder", _RecordingChartBuilder)

    replicate_stats = [{"ligand": "LigA", "receptor": "REC1", "affinity_best": -7.0}]
    lipinski_rows = [{"ligand": "LigA", "MW": 180.0, "LogP": 2.0, "HBD": 1, "HBA": 3}]
    admet_rows = [{"ligand": "LigA", "hia": 0.1, "hERG": 0.2}]

    pipe._generate_charts(replicate_stats, lipinski_rows, admet_rows)

    title = _RecordingChartBuilder.calls[0]["title"]
    assert "ADMET" in title
    assert title == "Profil Gabungan: Fisikokimia + ADMET + ΔG"


def test_generate_charts_judul_hanya_delta_g_tanpa_lipinski_tanpa_admet(tmp_path, sample_excels, monkeypatch):
    import chemflow.pipeline as pipeline_module
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path,
                          output_dir=tmp_path / "out", openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    _RecordingChartBuilder.calls = []
    monkeypatch.setattr(pipeline_module, "ChartBuilder", _RecordingChartBuilder)

    replicate_stats = [{"ligand": "LigA", "receptor": "REC1", "affinity_best": -7.0}]

    pipe._generate_charts(replicate_stats, lipinski_rows=[], admet_rows=[])

    title = _RecordingChartBuilder.calls[0]["title"]
    assert title == "Profil Gabungan: ΔG"
    assert "Fisikokimia" not in title
    assert "ADMET" not in title


def test_generate_charts_label_dibedakan_per_reseptor_saat_multi_reseptor(tmp_path, sample_excels, monkeypatch):
    """Nama ligan yang sama di lebih dari satu reseptor harus dibedakan pada label
    grafik, karena matplotlib menganggap label identik sebagai satu posisi kategori.
    Radar gabungan hanya memuat satu seri per ligan: reseptor dengan afinitas terbaik."""
    import chemflow.pipeline as pipeline_module
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path,
                          output_dir=tmp_path / "out", openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    _RecordingChartBuilder.calls = []
    _RecordingChartBuilder.bar_calls = []
    monkeypatch.setattr(pipeline_module, "ChartBuilder", _RecordingChartBuilder)

    replicate_stats = [
        {"ligand": "LigA", "receptor": "REC1", "affinity_best": -7.0},
        {"ligand": "LigA", "receptor": "REC2", "affinity_best": -9.0},
        {"ligand": "LigB", "receptor": "REC1", "affinity_best": -6.0},
    ]

    pipe._generate_charts(replicate_stats, lipinski_rows=[], admet_rows=[])

    bar_labels = {r["_display_label"] for r in _RecordingChartBuilder.bar_calls[0]["rows"]}
    assert bar_labels == {"LigA (REC1)", "LigA (REC2)", "LigB (REC1)"}

    radar_labels = {r["_display_label"] for r in _RecordingChartBuilder.calls[0]["rows"]}
    assert radar_labels == {"LigA (REC2)", "LigB (REC1)"}
    assert _RecordingChartBuilder.calls[0]["rank_by"] == "affinity_best"


def test_generate_charts_label_polos_saat_satu_reseptor(tmp_path, sample_excels, monkeypatch):
    import chemflow.pipeline as pipeline_module
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path,
                          output_dir=tmp_path / "out", openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    _RecordingChartBuilder.calls = []
    _RecordingChartBuilder.bar_calls = []
    monkeypatch.setattr(pipeline_module, "ChartBuilder", _RecordingChartBuilder)

    replicate_stats = [
        {"ligand": "LigA", "receptor": "REC1", "affinity_best": -7.0},
        {"ligand": "LigB", "receptor": "REC1", "affinity_best": -6.0},
    ]

    pipe._generate_charts(replicate_stats, lipinski_rows=[], admet_rows=[])

    bar_labels = {r["_display_label"] for r in _RecordingChartBuilder.bar_calls[0]["rows"]}
    assert bar_labels == {"LigA", "LigB"}  # tanpa reseptor tempel, satu reseptor saja tak perlu disambiguasi


def test_config_admet_file_dan_no_admet_konflik(tmp_path, sample_excels):
    ligand_path, receptor_path = sample_excels
    admet = tmp_path / "admet.csv"
    admet.write_text("MW,hERG\n1,0.1\n")
    with pytest.raises(ValueError, match="admet_file"):
        PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, admet_file=admet, run_admet=False)


def test_config_admet_file_tidak_ada_raise(tmp_path, sample_excels):
    ligand_path, receptor_path = sample_excels
    with pytest.raises(FileNotFoundError, match="ADMET"):
        PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, admet_file=tmp_path / "x.csv")


def test_config_figure_dpi_dan_format(tmp_path, sample_excels):
    ligand_path, receptor_path = sample_excels
    with pytest.raises(ValueError, match="figure_dpi"):
        PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, figure_dpi=10)
    with pytest.raises(ValueError, match="tidak didukung"):
        PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, figure_formats=("bmp",))
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, figure_formats=("svg",))
    assert cfg.figure_formats == ("png", "svg")


def _admet_pipeline(tmp_path, sample_excels, admet_frame):
    from chemflow.chem.ligand_preparer import LigandPrepResult
    from chemflow.io.excel_ligands import LigandRecord
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    admet_path = tmp_path / "admet.csv"
    admet_frame.to_csv(admet_path, index=False)
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, output_dir=tmp_path / "out",
                          openbabel_path=ligand_path, admet_file=admet_path)
    pipe = Pipeline(cfg)
    pipe._input_records = [LigandRecord(name="Etanol", smiles="CCO"), LigandRecord(name="Metanol", smiles="CO")]
    return pipe, LigandPrepResult


def test_run_admet_dari_file_memetakan_urutan_dan_menyaring_ligan_gagal(tmp_path, sample_excels):
    from types import SimpleNamespace

    frame = pd.DataFrame({"smiles": ["CCO", "CO"], "hERG": [0.1, 0.9]})
    pipe, _ = _admet_pipeline(tmp_path, sample_excels, frame)

    rows = pipe._run_admet({"Metanol": SimpleNamespace(smiles="CO")})
    assert [r["ligand"] for r in rows] == ["Metanol"]
    assert rows[0]["hERG"] == pytest.approx(0.9)


def test_run_admet_file_jumlah_baris_salah_menghentikan_pipeline_dengan_kode_1(tmp_path, sample_excels):
    frame = pd.DataFrame({"smiles": ["CCO"], "hERG": [0.1]})
    pipe, _ = _admet_pipeline(tmp_path, sample_excels, frame)

    with pytest.raises(ValueError, match="berisi 1 baris"):
        pipe._run_admet({})


def test_merge_native_reference_menulis_kompleks_baseline(tmp_path, sample_excels):
    from rdkit import Chem
    from chemflow.docking.grid_box import GridBox
    from chemflow.docking.docking_matrix import ReceptorDockingTarget
    from chemflow.io.pdb_fetcher import NativeLigand
    from chemflow.pipeline import Pipeline

    ligand_path, receptor_path = sample_excels
    cfg = PipelineConfig(ligand_excel=ligand_path, receptor_excel=receptor_path, output_dir=tmp_path / "out",
                          openbabel_path=ligand_path)
    pipe = Pipeline(cfg)

    receptor_clean = tmp_path / "clean.pdb"
    _make_receptor_clean_pdb(receptor_clean)
    target = ReceptorDockingTarget(key="TEST", pdb_code="TEST", receptor_pdbqt=tmp_path / "dock.pdbqt",
                                    receptor_clean_pdb=receptor_clean,
                                    grid_box=GridBox.from_manual(0, 0, 0, 20, 20, 20))

    native_mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    from rdkit.Chem import AllChem
    AllChem.EmbedMolecule(native_mol, randomSeed=1)
    native_block = Chem.MolToPDBBlock(native_mol)

    native = NativeLigand(chain="X", resname="ASP", resnum=1,
                           center_x=0.0, center_y=0.0, center_z=0.0, atom_lines=[])
    native.to_pdb_block = lambda: native_block

    rmsd_context = {"TEST": {"native": native, "grid_box": target.grid_box, "receptor_pdbqt": target.receptor_pdbqt}}

    pipe._merge_native_reference(rmsd_context, [target])

    from chemflow.utils.name_sanitizer import sanitize_filename
    out_path = cfg.complex_dir / "TEST" / f"NATIVE_{sanitize_filename(native.label)}_complex.pdb"
    assert out_path.exists()

    import json
    metadata = json.loads(out_path.with_suffix(".json").read_text())
    assert metadata["is_native"] is True


def test_ligand_preparer_end_to_end_tanpa_tool_eksternal(tmp_path):
    """LigandPreparer sampai tahap sebelum PDBQT (murni RDKit, tanpa obabel):
    gambar 2D, strip/netralkan, AddHs, embed, minimisasi MMFF94, Gasteiger."""
    from rdkit import Chem

    mol_2d = Chem.MolFromSmiles("CCO")
    assert mol_2d is not None

    from chemflow.chem.ligand_preparer import LigandPreparer

    class _StubConverter:
        def mol_to_pdb(self, mol, path):
            Chem.MolToPDBFile(mol, str(path))
            return path

        def pdb_to_pdbqt(self, pdb_path, output_pdbqt, is_receptor):
            output_pdbqt.write_text("REMARK stub pdbqt\n")
            return output_pdbqt

    preparer = LigandPreparer(_StubConverter())
    result = preparer.prepare("Etanol", "CCO", tmp_path, generate_image=False)

    assert result.mol.GetNumConformers() == 1
    assert result.force_field_used in ("MMFF94", "UFF")
    assert result.pdb_path.exists()
    assert result.pdbqt_path.exists()

    # Muatan Gasteiger harus sudah terhitung pada setiap atom.
    for atom in result.mol.GetAtoms():
        assert atom.HasProp("_GasteigerCharge")
