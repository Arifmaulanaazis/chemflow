"""Test SimilarityPlotter: bar, scatter vs delta-G, dan heatmap jejak kontak terklaster."""

from chemflow.similarity.plots import SimilarityPlotter
from chemflow.similarity.similarity import SimilarityResult


def _result(ligand, receptor="6LU7", overall=50.0, test_res=(), ref_res=("75-His", "102-Val"),
            affinity_test=None, affinity_ref=None):
    return SimilarityResult(
        receptor_key=receptor, ligand_name=ligand, reference_name="Native", n_aa_test=1, n_aa_ref=2,
        aa_similarity_pct=overall, int_aa_test=1, int_aa_ref=2, type_similarity_pct=overall / 2,
        overall_similarity_pct=overall, test_residues=list(test_res), reference_residues=list(ref_res),
        affinity_test=affinity_test, affinity_ref=affinity_ref,
    )


def _results():
    return [
        _result("Aspirin", overall=80.0, test_res=("75-His", "300-Tyr"), affinity_test=-6.0, affinity_ref=-12.0),
        _result("Ibuprofen", overall=40.0, test_res=("102-Val",), affinity_test=-7.5, affinity_ref=-12.0),
        _result("Naproxen", overall=20.0, test_res=("300-Tyr", "410-Leu"), affinity_test=-8.0, affinity_ref=-12.0),
    ]


def test_bar_similarity_menghasilkan_file(tmp_path):
    paths = SimilarityPlotter(tmp_path).bar_similarity(_results())
    assert [p.name for p in paths] == ["similaritas_bar.png"] and paths[0].exists()


def test_bar_similarity_kosong_return_list_kosong(tmp_path):
    assert SimilarityPlotter(tmp_path).bar_similarity([]) == []


def test_bar_similarity_dipotong_bila_ligan_banyak(tmp_path):
    results = [_result(f"L{i}", overall=float(i)) for i in range(7)]
    paths = SimilarityPlotter(tmp_path, max_rows=3).bar_similarity(results)
    assert [p.name for p in paths] == ["similaritas_bar_part01of03.png", "similaritas_bar_part02of03.png",
                                       "similaritas_bar_part03of03.png"]


def test_footprint_heatmaps_dipotong_bila_residu_banyak(tmp_path):
    residues = tuple(f"{i}-Ala" for i in range(1, 9))
    results = [_result("Aspirin", test_res=residues, ref_res=residues), _result("Ibuprofen", test_res=residues[:4]),
               _result("Naproxen", test_res=residues[2:])]
    paths = SimilarityPlotter(tmp_path, max_cols=4).footprint_heatmaps(results)
    assert len(paths) == 3 and all(p.exists() for p in paths)  # 8 residu + 2 residu referensi = 10 kolom


def test_scatter_vs_deltag_menghasilkan_file(tmp_path):
    path = SimilarityPlotter(tmp_path).scatter_vs_deltag(_results())
    assert path is not None and path.exists()


def test_scatter_vs_deltag_multi_reseptor(tmp_path):
    results = _results() + [_result("Aspirin", receptor="3LN1", overall=60.0, affinity_test=-8.0, affinity_ref=-12.5)]
    assert SimilarityPlotter(tmp_path).scatter_vs_deltag(results).exists()


def test_scatter_vs_deltag_tanpa_afinitas_return_none(tmp_path):
    results = [_result("Aspirin"), _result("Ibuprofen")]
    assert SimilarityPlotter(tmp_path).scatter_vs_deltag(results) is None


def test_footprint_heatmaps_satu_file_per_reseptor(tmp_path):
    results = _results() + [_result("Aspirin", receptor="3LN1", test_res=("75-His",))]
    paths = SimilarityPlotter(tmp_path).footprint_heatmaps(results)
    assert {p.name for p in paths} == {"similaritas_jejak_6LU7.png", "similaritas_jejak_3LN1.png"}
    assert all(p.exists() for p in paths)


def test_footprint_heatmaps_tanpa_residu_dilewati(tmp_path):
    results = [_result("Aspirin", test_res=(), ref_res=())]
    assert SimilarityPlotter(tmp_path).footprint_heatmaps(results) == []


def test_plot_all_mengumpulkan_semua_grafik(tmp_path):
    paths = SimilarityPlotter(tmp_path, formats=("png", "svg")).plot_all(_results())
    names = {p.name for p in paths}
    assert {"similaritas_bar.png", "similaritas_vs_deltag.png", "similaritas_jejak_6LU7.png"} <= names
    assert (tmp_path / "similaritas_bar.svg").exists()


def test_plot_all_kosong(tmp_path):
    assert SimilarityPlotter(tmp_path).plot_all([]) == []
