"""Test pengecekan struktural backbone asam amino (is_polymer_backbone_complete)."""

from chemflow.utils.residue_backbone import is_polymer_backbone_complete


def test_lengkap_backbone_standar():
    elems = {"N": "N", "CA": "C", "C": "C", "O": "O", "CB": "C"}
    assert is_polymer_backbone_complete(elems) is True


def test_residu_termodifikasi_mse_tetap_lengkap():
    # MSE (selenometionin) tetap punya N-CA-C standar meski sidechain beda (ada Se).
    elems = {"N": "N", "CA": "C", "C": "C", "O": "O", "CB": "C", "CG": "C", "SE": "SE", "CE": "C"}
    assert is_polymer_backbone_complete(elems) is True


def test_ligan_mirip_asam_amino_tanpa_ca_tidak_lengkap():
    # GABA-like: punya N dan C tapi tidak ada CA -> bukan bagian backbone.
    elems = {"N": "N", "C1": "C", "C2": "C", "C3": "C", "O1": "O", "O2": "O"}
    assert is_polymer_backbone_complete(elems) is False


def test_ion_kalsium_bernama_atom_ca_tidak_salah_dikenali():
    # Ion Ca2+ punya nama atom PDB literal "CA" tapi elemen sebenarnya kalsium,
    # dan tidak ada atom N/C pendamping -> harus False.
    elems = {"CA": "CA"}
    assert is_polymer_backbone_complete(elems) is False


def test_residu_kosong():
    assert is_polymer_backbone_complete({}) is False


def test_ca_elemen_salah_tidak_lolos():
    # Nama atom "CA" ada tapi elemennya bukan karbon (edge case data korup) -> False.
    elems = {"N": "N", "CA": "CA", "C": "C"}
    assert is_polymer_backbone_complete(elems) is False
