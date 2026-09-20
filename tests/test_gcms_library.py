"""Test pustaka GC-MS: pencocokan nama, alergen UE, pustaka pengguna, Kovats, pencocokan RT dan RI."""

import numpy as np
import pandas as pd
import pytest
from rdkit import Chem

from chemflow.gcms import library as lib


def test_kunci_nama_membuang_stereo_dan_tanda_baca():
    assert lib.name_key("(E)-Cinnamal") == lib.name_key("cinnamal")
    assert lib.name_key("d-Limonene") == "limonene"
    assert lib.name_key("Benzoic acid, phenylmethyl ester") == "benzoicacidphenylmethylester"


def test_dua_puluh_empat_alergen_tunggal_dengan_smiles_valid():
    assert len(lib.EU_ALLERGENS) == 24
    assert len({a.cas for a in lib.EU_ALLERGENS}) == 24
    for allergen in lib.EU_ALLERGENS:
        assert Chem.MolFromSmiles(allergen.smiles) is not None, allergen.name


def test_formula_molekul_alergen_sesuai_rujukan():
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula

    expected = {"Limonene": "C10H16", "Linalool": "C10H18O", "Coumarin": "C9H6O2", "Eugenol": "C10H12O2",
                "Benzyl benzoate": "C14H12O2", "Citral": "C10H16O", "Geraniol": "C10H18O", "Farnesol": "C15H26O",
                "Cinnamal": "C9H8O", "Butylphenyl methylpropional": "C14H20O", "Hexyl cinnamal": "C15H20O",
                "Amyl cinnamal": "C14H18O", "Benzyl salicylate": "C14H12O3", "Citronellol": "C10H20O",
                "Isoeugenol": "C10H12O2", "Anisyl alcohol": "C8H10O2", "Benzyl alcohol": "C7H8O",
                "Methyl 2-octynoate": "C9H14O2", "Hydroxycitronellal": "C10H20O2", "Benzyl cinnamate": "C16H14O2",
                "Amylcinnamyl alcohol": "C14H20O", "Cinnamyl alcohol": "C9H10O", "alpha-Isomethyl ionone": "C14H22O",
                "Hydroxyisohexyl 3-cyclohexene carboxaldehyde": "C13H22O2"}
    by_name = {a.name: a for a in lib.EU_ALLERGENS}
    assert set(expected) == set(by_name)
    for name, formula in expected.items():
        assert CalcMolFormula(Chem.MolFromSmiles(by_name[name].smiles)) == formula, name


def test_cocok_nama_persis_alias_nist_dan_cas():
    hits = lib.match_by_name(["Linalool", "Linalool oxide", "Benzenepropanal, 4-(1,1-dimethylethyl)-.alpha.-methyl-", "", "x"],
                             ["", "", "", "91-64-5", "138-86-3"])
    assert hits[0].name == "Linalool" and 1 not in hits
    assert hits[2].name == "Butylphenyl methylpropional"
    assert hits[3].name == "Coumarin" and hits[4].name == "Limonene"


def test_alias_d_limonene_dan_lilial():
    hits = lib.match_by_name(["d-Limonene", "Lilial"], ["", ""])
    assert {h.name for h in hits.values()} == {"Limonene", "Butylphenyl methylpropional"}


def _write_library(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_muat_pustaka_dengan_judul_bervariasi(tmp_path):
    path = _write_library(tmp_path / "lib.csv", {"Nama": ["Limonene", "Linalool"], "RT (min)": [8.0, 9.5],
                                                 "CAS#": ["5989-27-5", "78-70-6"], "SMILES": ["CC1=CCC(CC1)C(C)=C", "CC(C)=CCCC(C)(O)C=C"]})
    compounds = lib.load_library(path)
    assert [(c.name, c.rt, c.cas) for c in compounds] == [("Limonene", 8.0, "5989-27-5"), ("Linalool", 9.5, "78-70-6")]
    assert compounds[0].smiles.startswith("CC1")


def test_pustaka_tanpa_kolom_nama_ditolak(tmp_path):
    with pytest.raises(ValueError, match="kolom nama"):
        lib.load_library(_write_library(tmp_path / "x.csv", {"a": [1], "b": [2]}))
    with pytest.raises(FileNotFoundError):
        lib.load_library(tmp_path / "tidak-ada.csv")


def test_pustaka_excel(tmp_path):
    path = tmp_path / "lib.xlsx"
    pd.DataFrame({"name": ["Coumarin"], "ri": [1432.0]}).to_excel(path, index=False)
    assert lib.load_library(path)[0].ri == 1432.0


def test_cocok_lewat_rt_terdekat_satu_senyawa_satu_fitur():
    compounds = [lib.Compound("A", rt=8.00), lib.Compound("B", rt=9.50)]
    matched = lib.match_by_retention([7.98, 8.03, 9.52, 12.0], None, compounds, rt_tolerance=0.05)
    assert matched[0][0].name == "A" and matched[2][0].name == "B"
    assert 1 not in matched and 3 not in matched


def test_cocok_lewat_ri_didahulukan_bila_tersedia():
    compounds = [lib.Compound("A", ri=1000.0, rt=99.0)]
    matched = lib.match_by_retention([8.0, 9.0], np.array([1004.0, 1200.0]), compounds, rt_tolerance=0.05, ri_tolerance=10.0)
    assert list(matched) == [0]


def test_kovats_interpolasi_dan_di_luar_deret_nan():
    carbons, times = np.array([8.0, 9.0, 10.0]), np.array([5.0, 8.0, 12.0])
    ri = lib.kovats_index([5.0, 6.5, 10.0, 4.0, 13.0], carbons, times)
    assert ri[:3].tolist() == pytest.approx([800.0, 850.0, 950.0])
    assert np.isnan(ri[3]) and np.isnan(ri[4])


def test_muat_alkana_dan_validasi(tmp_path):
    path = tmp_path / "alk.csv"
    pd.DataFrame({"carbon": [10, 8, 9], "rt": [12.0, 5.0, 8.0]}).to_csv(path, index=False)
    carbons, times = lib.load_alkanes(path)
    assert carbons.tolist() == [8.0, 9.0, 10.0] and times.tolist() == [5.0, 8.0, 12.0]
    pd.DataFrame({"carbon": [8, 9]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="carbon"):
        lib.load_alkanes(path)
    pd.DataFrame({"carbon": [8, 9], "rt": [5.0, 6.0]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="minimal 3"):
        lib.load_alkanes(path)
