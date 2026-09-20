"""Test compute_similarity (Pratama et al. 2021, Eq. 2) & SimilarityAnalyzer."""

import json

import pandas as pd
import pytest
from openpyxl import Workbook

from chemflow.similarity.biovia_reader import ProteinLigandContact
from chemflow.similarity.similarity import SimilarityAnalyzer, compute_similarity, export_similarity_results


def _contact(resnum, resname, interaction_type):
    return ProteinLigandContact(resnum=resnum, resname=resname, interaction_type=interaction_type)


def test_compute_similarity_identik_100_persen():
    ref = [_contact(75, "HIS", "Conventional Hydrogen Bond"), _contact(102, "VAL", "Van der Waals")]
    test = [_contact(75, "HIS", "Conventional Hydrogen Bond"), _contact(102, "VAL", "Van der Waals")]

    result = compute_similarity(test, ref, ligand_name="Test", reference_name="Ref")
    assert result.aa_similarity_pct == 100.0
    assert result.type_similarity_pct == 100.0
    assert result.overall_similarity_pct == 100.0
    assert result.n_aa_ref == 2
    assert result.n_aa_test == 2


def test_compute_similarity_tidak_ada_overlap_0_persen():
    ref = [_contact(75, "HIS", "Conventional Hydrogen Bond")]
    test = [_contact(999, "GLU", "Van der Waals")]

    result = compute_similarity(test, ref)
    assert result.aa_similarity_pct == 0.0
    assert result.type_similarity_pct == 0.0
    assert result.overall_similarity_pct == 0.0


def test_compute_similarity_residu_sama_tipe_beda():
    """Residu cocok (identitas), tapi tipe interaksi berbeda -> nAA tinggi, intAA rendah.

    Contoh angka dihitung manual (bukan direproduksi dari tabel paper):
    referensi punya 4 residu unik dengan 4 interaksi (1 tipe per residu).
    Ligan uji berinteraksi dengan semua 4 residu yang sama (nAAtest=4,
    nAAref=4 -> 100%), tapi hanya 1 dari 4 pasangan (residu, tipe) yang
    persis sama dengan referensi (intAAtest=1, intAAref=4 -> 25%).
    Overall = 0.5*100 + 0.5*25 = 62.5%.
    """
    ref = [
        _contact(75, "HIS", "Conventional Hydrogen Bond"),
        _contact(102, "VAL", "Van der Waals"),
        _contact(106, "ARG", "Van der Waals"),
        _contact(178, "GLN", "Conventional Hydrogen Bond"),
    ]
    test = [
        _contact(75, "HIS", "Conventional Hydrogen Bond"),  # cocok residu + tipe
        _contact(102, "VAL", "Pi-Alkyl"),                    # cocok residu, tipe beda
        _contact(106, "ARG", "Pi-Sigma"),                    # cocok residu, tipe beda
        _contact(178, "GLN", "Pi-Alkyl"),                    # cocok residu, tipe beda
    ]

    result = compute_similarity(test, ref)
    assert result.n_aa_test == 4
    assert result.n_aa_ref == 4
    assert result.aa_similarity_pct == 100.0
    assert result.int_aa_test == 1
    assert result.int_aa_ref == 4
    assert result.type_similarity_pct == 25.0
    assert result.overall_similarity_pct == 62.5


def test_compute_similarity_referensi_kosong_raise():
    with pytest.raises(ValueError, match="referensi"):
        compute_similarity([_contact(1, "ALA", "Van der Waals")], [], reference_name="RefKosong")


def test_compute_similarity_matched_residues_dan_interactions_label():
    ref = [_contact(75, "HIS", "Conventional Hydrogen Bond")]
    test = [_contact(75, "HIS", "Conventional Hydrogen Bond")]

    result = compute_similarity(test, ref)
    assert result.matched_residues == ["75-His"]
    assert result.matched_interactions == ["75-His (Conventional Hydrogen Bond)"]


def _write_biovia_excel(path, contact_specs, ligand_chain="X", ligand_resnum=1, ligand_resname="LIG"):
    """contact_specs: list of (resnum, resname, atom_name_protein, interaction_type)."""
    wb = Workbook()
    ws = wb.active
    for i, (resnum, resname, atom_name, itype) in enumerate(contact_specs):
        from_spec = f"A:{resname}{resnum}:{atom_name}"
        to_spec = f"{ligand_chain}:{ligand_resname}{ligand_resnum}:C{i}"
        ws.append([f"{from_spec} - {to_spec}", "Yes", "0 255 0", "Ligand Non-bond Monitor", i,
                   "Category", itype, from_spec, "H-Donor", to_spec, "H-Acceptor"])
    wb.save(path)


def _write_metadata(pdb_path, ligand_name, ligand_chain, ligand_resname, is_native):
    metadata = {"ligand_name": ligand_name, "ligand_code": "", "ligand_chain": ligand_chain,
                "ligand_resname": ligand_resname, "is_native": is_native}
    pdb_path.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")


def test_similarity_analyzer_end_to_end(tmp_path):
    output_dir = tmp_path / "hasil"
    complex_dir = output_dir / "complexes" / "6LU7"
    complex_dir.mkdir(parents=True)

    native_pdb = complex_dir / "NATIVE_ASP_X1_complex.pdb"
    native_pdb.write_text("REMARK stub\n")
    _write_metadata(native_pdb, ligand_name="Celecoxib", ligand_chain="X", ligand_resname="ASP", is_native=True)

    test_pdb = complex_dir / "Aspirin_complex.pdb"
    test_pdb.write_text("REMARK stub\n")
    _write_metadata(test_pdb, ligand_name="Aspirin", ligand_chain="X", ligand_resname="ASP", is_native=False)

    interactions_dir = output_dir / "interaksi" / "6LU7"
    interactions_dir.mkdir(parents=True)
    _write_biovia_excel(interactions_dir / "NATIVE_ASP_X1_complex_interaksi.xlsx", [
        (75, "HIS", "NE2", "Conventional Hydrogen Bond"),
        (102, "VAL", "CA", "Van der Waals"),
    ])
    _write_biovia_excel(interactions_dir / "Aspirin_complex_interaksi.xlsx", [
        (75, "HIS", "NE2", "Conventional Hydrogen Bond"),
    ])

    results = SimilarityAnalyzer().analyze_output_dir(output_dir)
    assert len(results) == 1
    r = results[0]
    assert r.ligand_name == "Aspirin"
    assert r.reference_name == "Celecoxib"
    assert r.receptor_key == "6LU7"
    assert r.n_aa_ref == 2
    assert r.n_aa_test == 1
    assert r.aa_similarity_pct == 50.0


def test_similarity_analyzer_tanpa_native_dilewati_dengan_warning(tmp_path):
    output_dir = tmp_path / "hasil"
    complex_dir = output_dir / "complexes" / "6LU7"
    complex_dir.mkdir(parents=True)

    test_pdb = complex_dir / "Aspirin_complex.pdb"
    test_pdb.write_text("REMARK stub\n")
    _write_metadata(test_pdb, ligand_name="Aspirin", ligand_chain="X", ligand_resname="ASP", is_native=False)

    results = SimilarityAnalyzer().analyze_output_dir(output_dir)
    assert results == []


def test_similarity_analyzer_file_interaksi_belum_ada_dilewati(tmp_path):
    output_dir = tmp_path / "hasil"
    complex_dir = output_dir / "complexes" / "6LU7"
    complex_dir.mkdir(parents=True)

    native_pdb = complex_dir / "NATIVE_ASP_X1_complex.pdb"
    native_pdb.write_text("REMARK stub\n")
    _write_metadata(native_pdb, ligand_name="Celecoxib", ligand_chain="X", ligand_resname="ASP", is_native=True)

    test_pdb = complex_dir / "Aspirin_complex.pdb"
    test_pdb.write_text("REMARK stub\n")
    _write_metadata(test_pdb, ligand_name="Aspirin", ligand_chain="X", ligand_resname="ASP", is_native=False)

    # Folder interaksi/ belum ada sama sekali.
    results = SimilarityAnalyzer().analyze_output_dir(output_dir)
    assert results == []


def test_similarity_analyzer_complexes_tidak_ada_raise(tmp_path):
    with pytest.raises(FileNotFoundError):
        SimilarityAnalyzer().analyze_output_dir(tmp_path / "belum_pernah_run")


def test_export_similarity_results_menghasilkan_file(tmp_path):
    ref = [_contact(75, "HIS", "Conventional Hydrogen Bond")]
    test = [_contact(75, "HIS", "Conventional Hydrogen Bond")]
    result = compute_similarity(test, ref, ligand_name="Aspirin", reference_name="Celecoxib", receptor_key="6LU7")

    out_path = tmp_path / "similaritas.xlsx"
    export_similarity_results([result], out_path)
    assert out_path.exists()

    import pandas as pd
    df = pd.read_excel(out_path)
    assert df.iloc[0]["ligand"] == "Aspirin"
    assert df.iloc[0]["overall_similarity_pct"] == 100.0


def test_export_similarity_results_kosong_tetap_menghasilkan_file_dengan_header(tmp_path):
    out_path = tmp_path / "similaritas.xlsx"
    export_similarity_results([], out_path)
    assert out_path.exists()

    import pandas as pd
    df = pd.read_excel(out_path)
    assert "ligand" in df.columns
    assert len(df) == 0


def test_delta_g_selisih_uji_dikurangi_referensi():
    ref = [_contact(75, "HIS", "Conventional Hydrogen Bond")]
    result = compute_similarity(ref, ref, affinity_test=-9.5, affinity_ref=-12.5)
    assert result.delta_g == pytest.approx(3.0)


def test_delta_g_none_jika_afinitas_tidak_lengkap():
    ref = [_contact(75, "HIS", "Conventional Hydrogen Bond")]
    assert compute_similarity(ref, ref).delta_g is None
    assert compute_similarity(ref, ref, affinity_test=-9.0).delta_g is None


def test_residu_uji_dan_referensi_tersimpan_urut_nomor():
    ref = [_contact(102, "VAL", "Van der Waals"), _contact(75, "HIS", "Conventional Hydrogen Bond")]
    test = [_contact(300, "TYR", "Pi-Pi Stacked"), _contact(75, "HIS", "Conventional Hydrogen Bond")]
    result = compute_similarity(test, ref)
    assert result.reference_residues == ["75-His", "102-Val"]
    assert result.test_residues == ["75-His", "300-Tyr"]


def _write_hasil_workbook(output_dir, test_affinity, redock_affinity):
    output_dir.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_dir / "hasil_chemflow.xlsx") as writer:
        pd.DataFrame([{"ligand": "Aspirin", "receptor": "6LU7", "affinity_best": test_affinity}]).to_excel(
            writer, sheet_name="Statistik Replikasi", index=False)
        pd.DataFrame([{"receptor": "6LU7", "redock_affinity": redock_affinity}]).to_excel(
            writer, sheet_name="Validasi RMSD", index=False)


def test_analyzer_membaca_afinitas_untuk_delta_g(tmp_path):
    output_dir = tmp_path / "hasil"
    complex_dir = output_dir / "complexes" / "6LU7"
    complex_dir.mkdir(parents=True)
    for name, ligand, native in (("NATIVE_ASP_X1_complex", "Celecoxib", True), ("Aspirin_complex", "Aspirin", False)):
        pdb = complex_dir / f"{name}.pdb"
        pdb.write_text("REMARK stub\n")
        _write_metadata(pdb, ligand_name=ligand, ligand_chain="X", ligand_resname="ASP", is_native=native)

    interactions = output_dir / "interaksi" / "6LU7"
    interactions.mkdir(parents=True)
    contacts = [(75, "HIS", "NE2", "Conventional Hydrogen Bond")]
    _write_biovia_excel(interactions / "NATIVE_ASP_X1_complex_interaksi.xlsx", contacts)
    _write_biovia_excel(interactions / "Aspirin_complex_interaksi.xlsx", contacts)
    _write_hasil_workbook(output_dir, test_affinity=-6.4, redock_affinity=-12.5)

    result = SimilarityAnalyzer().analyze_output_dir(output_dir)[0]
    assert result.affinity_test == pytest.approx(-6.4)
    assert result.affinity_ref == pytest.approx(-12.5)
    assert result.delta_g == pytest.approx(6.1)


def test_analyzer_delta_g_dari_docking_native_bila_tanpa_sheet_rmsd(tmp_path):
    output_dir = tmp_path / "hasil"
    complex_dir = output_dir / "complexes" / "6LU7"
    complex_dir.mkdir(parents=True)
    for name, ligand, native in (("NATIVE_ASP_X1_complex", "Celecoxib", True), ("Aspirin_complex", "Aspirin", False)):
        pdb = complex_dir / f"{name}.pdb"
        pdb.write_text("REMARK stub\n")
        _write_metadata(pdb, ligand_name=ligand, ligand_chain="X", ligand_resname="ASP", is_native=native)
    interactions = output_dir / "interaksi" / "6LU7"
    interactions.mkdir(parents=True)
    contacts = [(75, "HIS", "NE2", "Conventional Hydrogen Bond")]
    _write_biovia_excel(interactions / "NATIVE_ASP_X1_complex_interaksi.xlsx", contacts)
    _write_biovia_excel(interactions / "Aspirin_complex_interaksi.xlsx", contacts)
    with pd.ExcelWriter(output_dir / "hasil_chemflow.xlsx") as writer:
        pd.DataFrame([
            {"ligand": "Aspirin", "group": "AINS", "receptor": "6LU7", "affinity_best": -6.4},
            {"ligand": "NATIVE_ASP_X1", "group": "Native", "receptor": "6LU7", "affinity_best": -12.5},
        ]).to_excel(writer, sheet_name="Statistik Replikasi", index=False)

    result = SimilarityAnalyzer().analyze_output_dir(output_dir)[0]
    assert result.affinity_ref == pytest.approx(-12.5)
    assert result.delta_g == pytest.approx(6.1)


def test_analyzer_sheet_rmsd_menang_atas_docking_native(tmp_path):
    output_dir = tmp_path / "hasil"
    output_dir.mkdir()
    with pd.ExcelWriter(output_dir / "hasil_chemflow.xlsx") as writer:
        pd.DataFrame([
            {"ligand": "NATIVE_X", "group": "Native", "receptor": "6LU7", "affinity_best": -9.0},
        ]).to_excel(writer, sheet_name="Statistik Replikasi", index=False)
        pd.DataFrame([{"receptor": "6LU7", "redock_affinity": -11.0}]).to_excel(
            writer, sheet_name="Validasi RMSD", index=False)
    _, reference = SimilarityAnalyzer()._load_affinities(output_dir)
    assert reference == {"6LU7": -11.0}


def test_analyzer_tanpa_workbook_delta_g_kosong(tmp_path):
    output_dir = tmp_path / "hasil"
    complex_dir = output_dir / "complexes" / "6LU7"
    complex_dir.mkdir(parents=True)
    for name, ligand, native in (("NATIVE_ASP_X1_complex", "Celecoxib", True), ("Aspirin_complex", "Aspirin", False)):
        pdb = complex_dir / f"{name}.pdb"
        pdb.write_text("REMARK stub\n")
        _write_metadata(pdb, ligand_name=ligand, ligand_chain="X", ligand_resname="ASP", is_native=native)
    interactions = output_dir / "interaksi" / "6LU7"
    interactions.mkdir(parents=True)
    contacts = [(75, "HIS", "NE2", "Conventional Hydrogen Bond")]
    _write_biovia_excel(interactions / "NATIVE_ASP_X1_complex_interaksi.xlsx", contacts)
    _write_biovia_excel(interactions / "Aspirin_complex_interaksi.xlsx", contacts)

    assert SimilarityAnalyzer().analyze_output_dir(output_dir)[0].delta_g is None


def test_export_memuat_kolom_delta_g(tmp_path):
    ref = [_contact(75, "HIS", "Conventional Hydrogen Bond")]
    result = compute_similarity(ref, ref, ligand_name="Aspirin", affinity_test=-6.4, affinity_ref=-12.5)
    out = tmp_path / "similaritas.xlsx"
    export_similarity_results([result], out)
    df = pd.read_excel(out)
    assert df.iloc[0]["delta_g"] == pytest.approx(6.1)
    assert df.iloc[0]["affinity_ref"] == pytest.approx(-12.5)
