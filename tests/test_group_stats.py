"""Test agregasi per grup (ΔG, ADMET, fisikokimia) dan pembanding native."""

import pytest

from chemflow.analytics import group_stats as gs

GROUP_OF = {"A1": "G1", "A2": "G1", "B1": "G2", "B2": "G2", "NATIVE_X": "Native"}

STATS = [
    {"ligand": "A1", "receptor": "R1", "affinity_best": -8.0},
    {"ligand": "A2", "receptor": "R1", "affinity_best": -6.0},
    {"ligand": "B1", "receptor": "R1", "affinity_best": -9.5},
    {"ligand": "B2", "receptor": "R1", "affinity_best": -7.0},
    {"ligand": "NATIVE_X", "receptor": "R1", "affinity_best": -9.0},
    {"ligand": "A1", "receptor": "R2", "affinity_best": -5.0},
    {"ligand": "B1", "receptor": "R2", "affinity_best": -7.5},
]

ADMET = [
    {"ligand": "A1", "hERG": 0.1, "DILI": 0.1, "Ames": 0.1},     # baik semua
    {"ligand": "A2", "hERG": 0.9, "DILI": 0.9, "Ames": 0.9},     # buruk semua
    {"ligand": "B1", "hERG": 0.1, "DILI": 0.1, "Ames": 0.1},
    {"ligand": "B2", "hERG": 0.1, "DILI": 0.1, "Ames": 0.1},
    {"ligand": "NATIVE_X", "hERG": 0.9, "DILI": 0.1, "Ames": 0.1},
]


def test_group_label_dan_urutan_native_di_awal_atau_akhir():
    assert gs.group_label("  ") == gs.NO_GROUP and gs.group_label(None) == gs.NO_GROUP
    assert gs.group_order(GROUP_OF) == ["Native", "G1", "G2"]
    assert gs.group_order(GROUP_OF, native_last=True) == ["G1", "G2", "Native"]


def test_affinities_by_group_receptor_mengeluarkan_native_kecuali_diminta():
    by_receptor = gs.affinities_by_group_receptor(STATS, GROUP_OF)
    assert by_receptor["R1"] == {"G1": [-8.0, -6.0], "G2": [-9.5, -7.0]}
    assert "Native" in gs.affinities_by_group_receptor(STATS, GROUP_OF, include_native=True)["R1"]


def test_native_affinity_by_receptor_dan_fraksi_lebih_baik():
    native = gs.native_affinity_by_receptor(STATS, GROUP_OF)
    assert native == {"R1": -9.0}
    share = gs.fraction_better_than_native(gs.affinities_by_group_receptor(STATS, GROUP_OF), native)
    assert share == {"R1": {"G1": 0.0, "G2": 50.0}}     # R2 tanpa native -> tidak ada


def test_add_delta_vs_native():
    rows = {(r["ligand"], r["receptor"]): r["delta_vs_native"] for r in gs.add_delta_vs_native(STATS, GROUP_OF)}
    assert rows[("A1", "R1")] == pytest.approx(1.0)
    assert rows[("B1", "R1")] == pytest.approx(-0.5)
    assert rows[("NATIVE_X", "R1")] is None
    assert rows[("A1", "R2")] is None


def test_flag_scores_by_group_rata_rata_skor_baik_sedang_buruk():
    scores = gs.flag_scores_by_group(ADMET, GROUP_OF, "Toksisitas")
    assert set(scores) == {"G1", "G2", "Native"}
    assert set(scores["G1"].values()) == {0.5}            # satu ligan baik (1) dan satu buruk (0)
    assert set(scores["G2"].values()) == {1.0}            # kedua ligan baik
    assert sorted(scores["Native"].values())[0] == 0.0    # hERG native buruk
    assert max(scores["Native"].values()) == 1.0


def test_category_scores_by_group_membedakan_grup_baik_dan_buruk():
    summary = gs.category_scores_by_group(ADMET, GROUP_OF)
    assert summary["G2"]["Toksisitas"] > summary["G1"]["Toksisitas"]
    assert summary["Native"]["Toksisitas"] < summary["G2"]["Toksisitas"]


def test_flag_counts_by_group_persen_tiga_kelas():
    counts = gs.flag_counts_by_group(ADMET, GROUP_OF, "Toksisitas")
    for group in ("G1", "G2", "Native"):
        for shares in counts[group].values():
            assert len(shares) == 3 and sum(shares) == pytest.approx(100.0)


def test_property_by_group():
    rows = [{"ligand": "A1", "MW": 100.0}, {"ligand": "A2", "MW": 200.0}, {"ligand": "B1", "MW": None}]
    assert gs.property_by_group(rows, GROUP_OF, "MW") == {"G1": [100.0, 200.0]}


def test_with_group_menyisipkan_kolom_setelah_ligan():
    rows = gs.with_group([{"ligand": "A1", "x": 1}], GROUP_OF)
    assert list(rows[0]) == ["ligand", "group", "x"] and rows[0]["group"] == "G1"
    assert gs.with_group([{"ligand": "ZZZ"}], GROUP_OF)[0]["group"] == gs.NO_GROUP


def test_summarize_groups_dan_docking():
    lipinski = [{"ligand": "A1", "MW": 100.0, "LogP": 1.0, "HBD": 1, "HBA": 2, "Lolos_Ro5": True},
                {"ligand": "A2", "MW": 300.0, "LogP": 3.0, "HBD": 2, "HBA": 4, "Lolos_Ro5": False},
                {"ligand": "NATIVE_X", "MW": 500.0, "LogP": 4.0, "HBD": 3, "HBA": 6, "Lolos_Ro5": True}]
    rows = {r["grup"]: r for r in gs.summarize_groups(lipinski, ADMET, GROUP_OF)}
    assert rows["G1"]["n_ligan"] == 2 and rows["G1"]["lolos_Ro5_persen"] == 50.0
    assert rows["G1"]["MW_rata2"] == 200.0 and "ADMET_Toksisitas" in rows["G1"]

    docking = gs.summarize_docking_by_group(STATS, GROUP_OF)
    r1_g2 = next(r for r in docking if r["reseptor"] == "R1" and r["grup"] == "G2")
    assert r1_g2["dG_rata2"] == pytest.approx(-8.25) and r1_g2["dG_terbaik"] == -9.5
    assert r1_g2["dG_native"] == -9.0 and r1_g2["lebih_baik_dari_native_persen"] == 50.0
    native_row = next(r for r in docking if r["grup"] == "Native")
    assert "lebih_baik_dari_native_persen" not in native_row
