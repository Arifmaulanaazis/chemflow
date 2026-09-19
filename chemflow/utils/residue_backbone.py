"""
Pembeda struktural antara "residu HETATM ini sebenarnya bagian dari rantai
polipeptida" (asam amino termodifikasi/nonstandar, mis. MSE selenometionin,
SEP fosfoserin, dst.) dengan ligan/air/ion asli yang memang harus dibuang
saat preparasi reseptor.

File PDB mencatat residu nonkanonik sebagai HETATM walaupun secara kimia ia
tetap bagian dari backbone protein. Kode yang memperlakukan "HETATM" sebagai
sinonim "ligan yang boleh dihapus" adalah sumber bug klasik di pipeline
preparasi reseptor, bisa menghapus residu penting tanpa sengaja.

Deteksi di sini murni STRUKTURAL (apakah residu punya backbone N-CA-C
lengkap dengan elemen yang benar), bukan berbasis daftar nama residu.
Konsekuensinya: residu termodifikasi apa pun otomatis tergeneralisasi tanpa
perlu menambah nama residu baru ke suatu daftar hardcode.
"""

from __future__ import annotations

from typing import Dict


def is_polymer_backbone_complete(atom_elements: Dict[str, str]) -> bool:
    """Cek apakah satu residu memiliki backbone asam amino yang lengkap.

    Args:
        atom_elements: pemetaan nama-atom PDB (sudah di-strip, uppercase) ke
            simbol elemen (uppercase) untuk seluruh atom dalam satu residu,
            mis. ``{"N": "N", "CA": "C", "C": "C", "O": "O", "CB": "C"}``.

    Returns:
        ``True`` jika atom N, CA, dan C semuanya ada dengan elemen yang
        benar. Artinya residu ini secara kimia bagian dari rantai
        polipeptida, terlepas dari apakah PDB mencatatnya sebagai ATOM
        atau HETATM.

    Catatan batas kasus:
        - Ligan mirip-asam-amino yang kehilangan atom CA (mis. GABA/ABU,
          punya N dan C tapi tanpa CA) dengan benar mengembalikan ``False``.
        - Ion logam yang nama atomnya kebetulan "CA" (kalsium) juga dengan
          benar mengembalikan ``False`` karena tidak ada atom N/C
          pendampingnya.
    """
    return (
        atom_elements.get("N") == "N"
        and atom_elements.get("CA") == "C"
        and atom_elements.get("C") == "C"
    )
