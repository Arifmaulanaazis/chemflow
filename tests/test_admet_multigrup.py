"""ADMET untuk senyawa multi-grup: SMILES sama diprediksi sekali lalu disalin ke tiap grup menurut indeks kirim."""

from types import SimpleNamespace

import pandas as pd
import pytest

from chemflow.admet.admet_file import load_admet_rows
from chemflow.admet.dedup import canonical_key, describe_duplicates, fan_out, group_by_smiles
from chemflow.config import PipelineConfig
from chemflow.io.excel_ligands import LigandRecord, multi_group_compounds

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ASPIRIN_ALT = "OC(=O)c1ccccc1OC(C)=O"          # penulisan lain, molekul sama


def test_canonical_key_menyamakan_penulisan_berbeda():
    assert canonical_key(ASPIRIN) == canonical_key(ASPIRIN_ALT)
    assert canonical_key("CCO") != canonical_key(ASPIRIN)


def test_canonical_key_smiles_kosong_memakai_nama_dan_smiles_rusak_teks_asli():
    assert canonical_key("", "Aspirin") == canonical_key("  ", "aspirin")
    assert canonical_key("bukan-smiles((", "x") == "raw:bukan-smiles(("


def test_group_by_smiles_urutan_kemunculan_pertama():
    grouping = group_by_smiles([ASPIRIN, "CCO", ASPIRIN_ALT, "CCO", "CO"])
    assert grouping.unique_smiles == [ASPIRIN, "CCO", "CO"]
    assert grouping.index_of == [0, 1, 0, 1, 2]
    assert grouping.members == [[0, 2], [1, 3], [4]]
    assert grouping.n_duplicates == 2
    assert grouping.duplicated_groups() == [[0, 2], [1, 3]]


def test_group_by_smiles_tanpa_duplikat():
    grouping = group_by_smiles(["CCO", "CO"])
    assert grouping.n_duplicates == 0 and grouping.index_of == [0, 1]


def test_fan_out_menyalin_baris_ke_tiap_ligan_dengan_grup():
    grouping = group_by_smiles([ASPIRIN, "CCO", ASPIRIN])
    unique_rows = [{"hERG": 0.1, "smiles": ASPIRIN}, {"hERG": 0.9, "smiles": "CCO"}]
    rows = fan_out(unique_rows, grouping, ["Aspirin", "Etanol", "Aspirin_2"], ["G1", "G1", "G2"])
    assert [r["ligand"] for r in rows] == ["Aspirin", "Etanol", "Aspirin_2"]
    assert [r["group"] for r in rows] == ["G1", "G1", "G2"]
    assert rows[0]["hERG"] == rows[2]["hERG"] == 0.1
    assert list(rows[0])[:2] == ["ligand", "group"]


def test_fan_out_lewati_smiles_tanpa_hasil():
    grouping = group_by_smiles([ASPIRIN, "CCO"])
    rows = fan_out([None, {"hERG": 0.9}], grouping, ["A", "B"])
    assert [r["ligand"] for r in rows] == ["B"]


def test_describe_duplicates_menyebut_grup():
    grouping = group_by_smiles([ASPIRIN, "CCO", ASPIRIN])
    lines = describe_duplicates(grouping, ["Aspirin", "Etanol", "Aspirin_2"], ["G1", "G1", "G2"])
    assert lines == ["Aspirin (grup: G1, G2)"]


def test_multi_group_compounds_hanya_bila_grup_berbeda():
    records = [LigandRecord("Aspirin", "", "G1"), LigandRecord("aspirin", "", "G2"),
               LigandRecord("Etanol", "", "G1"), LigandRecord("Etanol", "", "G1")]
    assert multi_group_compounds(records) == {"Aspirin": ["G1", "G2"]}


def _write(tmp_path, frame, name="admet.csv"):
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return path


def test_load_admet_rows_file_berisi_baris_unik_disalin_ke_ligan_kembar(tmp_path):
    path = _write(tmp_path, pd.DataFrame({"smiles": [ASPIRIN, "CCO"], "hERG": [0.1, 0.9]}))
    rows = load_admet_rows(path, ["Aspirin", "Etanol", "Aspirin_2"], [ASPIRIN, "CCO", ASPIRIN])
    assert [r["ligand"] for r in rows] == ["Aspirin", "Etanol", "Aspirin_2"]
    assert [r["hERG"] for r in rows] == [0.1, 0.9, 0.1]


def test_load_admet_rows_file_posisional_tetap_bekerja_walau_ada_kembar(tmp_path):
    path = _write(tmp_path, pd.DataFrame({"smiles": [ASPIRIN, "CCO", ASPIRIN], "hERG": [0.1, 0.9, 0.3]}))
    rows = load_admet_rows(path, ["Aspirin", "Etanol", "Aspirin_2"], [ASPIRIN, "CCO", ASPIRIN])
    assert [r["hERG"] for r in rows] == [0.1, 0.9, 0.3]


def test_load_admet_rows_jumlah_tidak_cocok_menyebut_smiles_unik(tmp_path):
    path = _write(tmp_path, pd.DataFrame({"hERG": [0.1]}))
    with pytest.raises(ValueError, match=r"berisi 1 baris.*3 ligan \(2 SMILES unik\)"):
        load_admet_rows(path, ["A", "B", "A_2"], [ASPIRIN, "CCO", ASPIRIN])


def test_load_admet_rows_peringatan_urutan_memakai_smiles_unik(tmp_path, caplog):
    path = _write(tmp_path, pd.DataFrame({"raw_smiles": ["CCO", ASPIRIN], "hERG": [0.9, 0.1]}))  # urutan terbalik
    with caplog.at_level("WARNING"):
        load_admet_rows(path, ["Aspirin", "Etanol", "Aspirin_2"], [ASPIRIN, "CCO", ASPIRIN])
    assert "tidak cocok" in caplog.text


class _FakeScraper:
    """AdmetLabScraper palsu: catat SMILES terkirim, kembalikan satu baris per SMILES."""
    sent = []

    def __init__(self, *args, **kwargs):
        pass

    def run(self, smiles):
        _FakeScraper.sent.append(list(smiles))
        return pd.DataFrame({"raw_smiles": list(smiles), "hERG": [round(0.1 * (i + 1), 1) for i in range(len(smiles))]})


@pytest.fixture
def pipe(tmp_path, monkeypatch):
    import chemflow.pipeline as pipeline_module

    ligand = tmp_path / "ligan.xlsx"
    pd.DataFrame({"name": ["Aspirin"], "smiles": [ASPIRIN]}).to_excel(ligand, index=False)
    receptor = tmp_path / "reseptor.xlsx"
    pd.DataFrame({"pdb_code": ["1AKI"]}).to_excel(receptor, index=False)
    cfg = PipelineConfig(ligand_excel=ligand, receptor_excel=receptor, output_dir=tmp_path / "out",
                         openbabel_path=ligand, show_progress=False)
    _FakeScraper.sent = []
    monkeypatch.setattr(pipeline_module, "AdmetLabScraper", _FakeScraper)
    return pipeline_module.Pipeline(cfg), pipeline_module


def _set_records(pipeline, groups_by_name):
    pipeline._input_records = [LigandRecord(name=n, smiles="", group=g, safe_name=n) for n, g in groups_by_name]
    pipeline._group_of = {n: g for n, g in groups_by_name}


def test_scraper_hanya_mengirim_smiles_unik_dan_menyalin_hasil(pipe):
    pipeline, _ = pipe
    _set_records(pipeline, [("Aspirin", "G1"), ("Etanol", "G1"), ("Aspirin_2", "G2")])
    results = {"Aspirin": SimpleNamespace(smiles=ASPIRIN), "Etanol": SimpleNamespace(smiles="CCO"),
               "Aspirin_2": SimpleNamespace(smiles=ASPIRIN)}

    rows = pipeline._run_admet(results)

    assert _FakeScraper.sent == [[ASPIRIN, "CCO"]]
    assert [r["ligand"] for r in rows] == ["Aspirin", "Etanol", "Aspirin_2"]
    assert [r["group"] for r in rows] == ["G1", "G1", "G2"]
    assert rows[0]["hERG"] == rows[2]["hERG"]
    assert rows[1]["hERG"] != rows[0]["hERG"]


def test_scraper_resume_tidak_mengirim_ulang_smiles_yang_sudah_ada(pipe, tmp_path):
    import chemflow.pipeline as pipeline_module

    pipeline, _ = pipe
    _set_records(pipeline, [("Aspirin", "G1"), ("Etanol", "G1")])
    results = {"Aspirin": SimpleNamespace(smiles=ASPIRIN), "Etanol": SimpleNamespace(smiles="CCO")}
    pipeline._run_admet(results)
    assert len(_FakeScraper.sent) == 1

    resumed = pipeline_module.Pipeline(pipeline.cfg, resume=True)
    resumed._begin()
    _set_records(resumed, [("Aspirin", "G1"), ("Etanol", "G1"), ("Metanol", "G2")])
    results["Metanol"] = SimpleNamespace(smiles="CO")
    rows = resumed._run_admet(results)

    assert _FakeScraper.sent[1:] == [["CO"]]           # hanya SMILES baru yang dikirim
    assert {r["ligand"] for r in rows} == {"Aspirin", "Etanol", "Metanol"}


def test_scraper_jumlah_baris_tak_cocok_dicocokkan_lewat_raw_smiles(pipe, monkeypatch):
    pipeline, pipeline_module = pipe

    class _Reordered(_FakeScraper):
        def run(self, smiles):
            return pd.DataFrame({"raw_smiles": list(reversed(smiles)) + [smiles[0]], "hERG": [0.5, 0.4, 0.3]})

    monkeypatch.setattr(pipeline_module, "AdmetLabScraper", _Reordered)
    _set_records(pipeline, [("Aspirin", "G1"), ("Etanol", "G1")])
    rows = pipeline._run_admet({"Aspirin": SimpleNamespace(smiles=ASPIRIN), "Etanol": SimpleNamespace(smiles="CCO")})
    assert {r["ligand"]: r["hERG"] for r in rows} == {"Aspirin": 0.4, "Etanol": 0.5}


def test_scraper_batch_tak_bisa_dipetakan_dilewati(pipe, monkeypatch):
    pipeline, pipeline_module = pipe

    class _Broken(_FakeScraper):
        def run(self, smiles):
            return pd.DataFrame({"hERG": [0.1]})            # tanpa raw_smiles, jumlah tak cocok

    monkeypatch.setattr(pipeline_module, "AdmetLabScraper", _Broken)
    _set_records(pipeline, [("Aspirin", "G1"), ("Etanol", "G1")])
    assert pipeline._run_admet({"Aspirin": SimpleNamespace(smiles=ASPIRIN),
                                "Etanol": SimpleNamespace(smiles="CCO")}) == []
