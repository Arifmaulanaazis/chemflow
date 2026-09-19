"""
Kalkulasi sifat fisikokimia, dibatasi pada Lipinski's Rule of Five sesuai
kebutuhan pipeline, plus beberapa deskriptor tambahan yang dipakai sebagai
fitur numerik untuk PCA kemometrik (chemical-space).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LipinskiResult:
    """Hasil evaluasi Lipinski's Rule of Five untuk satu senyawa.

    Aturan (Lipinski et al. 1997): senyawa punya potensi absorpsi oral baik
    jika TIDAK melanggar lebih dari 1 dari 4 kriteria berikut:
      - Berat molekul (MW) <= 500 Da
      - LogP (koefisien partisi oktanol-air) <= 5
      - Donor ikatan hidrogen (HBD) <= 5
      - Akseptor ikatan hidrogen (HBA) <= 10
    """
    molecular_weight: float
    logp: float
    hbd: int
    hba: int
    violations: int

    @property
    def passes_ro5(self) -> bool:
        """True jika pelanggaran <= 1 (konvensi standar Ro5)."""
        return self.violations <= 1


@dataclass
class ExtendedDescriptors:
    """Deskriptor tambahan (bukan bagian Ro5), dipakai sebagai fitur
    numerik pada PCA ruang-kimia (chemical-space PCA)."""
    tpsa: float
    rotatable_bonds: int
    aromatic_rings: int
    fraction_csp3: float


class LipinskiCalculator:
    """Menghitung Lipinski Ro5 & deskriptor tambahan dari RDKit Mol."""

    @staticmethod
    def calculate(mol: Any) -> LipinskiResult:
        """Hitung sifat fisikokimia Ro5 dari sebuah RDKit Mol.

        Args:
            mol: RDKit ``Mol`` (tidak perlu conformer 3D, semua deskriptor
                di sini berbasis graf 2D/atom).

        Returns:
            ``LipinskiResult`` dengan jumlah pelanggaran Ro5.
        """
        from rdkit.Chem import Descriptors, rdMolDescriptors  # type: ignore

        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumLipinskiHBD(mol)
        hba = rdMolDescriptors.CalcNumLipinskiHBA(mol)

        violations = sum([mw > 500, logp > 5, hbd > 5, hba > 10])

        return LipinskiResult(
            molecular_weight=round(mw, 2),
            logp=round(logp, 2),
            hbd=hbd,
            hba=hba,
            violations=violations,
        )

    @staticmethod
    def calculate_extended(mol: Any) -> ExtendedDescriptors:
        """Hitung deskriptor tambahan untuk fitur PCA ruang-kimia.

        Args:
            mol: RDKit ``Mol``.

        Returns:
            ``ExtendedDescriptors``.
        """
        from rdkit.Chem import Descriptors, rdMolDescriptors  # type: ignore

        return ExtendedDescriptors(
            tpsa=round(Descriptors.TPSA(mol), 2),
            rotatable_bonds=rdMolDescriptors.CalcNumRotatableBonds(mol),
            aromatic_rings=rdMolDescriptors.CalcNumAromaticRings(mol),
            fraction_csp3=round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
        )
