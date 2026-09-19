"""
Preparasi ligan lengkap: dari SMILES sampai PDBQT siap docking.

Urutan tahap (gambar 2D diambil SEBELUM minimisasi, dari mol 2D asli hasil
parsing SMILES, bukan dari konformasi 3D yang sudah dioptimasi):

    SMILES -> mol 2D -> gambar 2D (PNG)
           -> strip garam & netralkan muatan
           -> tambah H (AddHs)
           -> embed 3D
           -> minimisasi MMFF94 (fallback UFF jika parameter MMFF94 tak
              tersedia untuk elemen dalam molekul)
           -> hitung muatan Gasteiger
           -> tulis PDB -> konversi PDBQT via OpenBabel (obabel -h;
              OpenBabel menghitung ulang muatan Gasteiger + membangun
              pohon torsi ligan secara internal saat menulis PDBQT)

Setiap tahap mencatat kegagalan sebagai warning dan, kecuali untuk tahap
yang benar-benar fatal (parsing SMILES gagal), TIDAK menghentikan seluruh
pipeline untuk satu ligan yang bermasalah; ligan itu ditandai gagal dan
ligan lain tetap diproses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from chemflow.chem.mol_converter import OpenBabelConverter
from chemflow.utils.name_sanitizer import sanitize_filename


@dataclass
class LigandPrepResult:
    """Ringkasan hasil preparasi satu ligan."""
    name: str
    smiles: str
    mol: Any                      # RDKit Mol final (dengan conformer + muatan Gasteiger)
    image_path: Optional[Path]
    pdb_path: Path
    pdbqt_path: Path
    force_field_used: str         # "MMFF94" atau "UFF" (fallback)
    minimized_energy: Optional[float]


class LigandPreparer:
    """Menjalankan seluruh pipeline preparasi satu ligan dari SMILES."""

    def __init__(self, obabel: OpenBabelConverter, logger: Optional[logging.Logger] = None) -> None:
        self._obabel = obabel
        self._log = logger or logging.getLogger(__name__)

    def prepare(
        self,
        name: str,
        smiles: str,
        output_dir: Path,
        *,
        force_field: str = "MMFF94",
        max_iterations: int = 1000,
        generate_image: bool = True,
    ) -> LigandPrepResult:
        """Jalankan seluruh pipeline preparasi untuk satu ligan.

        Args:
            name: nama senyawa (dipakai untuk nama file).
            smiles: string SMILES (harus valid, sudah di-resolve dari
                PubChem jika perlu, bukan tanggung jawab fungsi ini).
            output_dir: direktori tujuan (gambar, .pdb, .pdbqt).
            force_field: "MMFF94" (default, fallback otomatis ke UFF) atau "UFF".
            max_iterations: iterasi maksimum minimisasi.
            generate_image: buat gambar 2D sebelum minimisasi.

        Returns:
            ``LigandPrepResult`` berisi semua path & metadata hasil.

        Raises:
            ValueError: SMILES tidak valid (tahap fatal, tak ada fallback).
        """
        from rdkit import Chem  # type: ignore

        output_dir.mkdir(parents=True, exist_ok=True)
        stem = sanitize_filename(name)

        mol_2d = Chem.MolFromSmiles(smiles)
        if mol_2d is None:
            raise ValueError(f"SMILES tidak valid untuk '{name}': {smiles!r}")

        image_path: Optional[Path] = None
        if generate_image:
            image_path = output_dir / f"{stem}_2d.png"
            try:
                self._save_2d_image(mol_2d, image_path)
            except Exception as exc:
                self._log.warning(f"[{name}] Gagal membuat gambar 2D: {exc}")
                image_path = None

        mol = self._strip_and_neutralize(mol_2d, name)
        mol = self._add_hydrogens(mol, name)
        mol = self._embed_3d(mol, name)
        mol, ff_used, energy = self._minimize(mol, name, force_field, max_iterations)
        self._compute_gasteiger(mol, name)

        pdb_path = output_dir / f"{stem}.pdb"
        pdbqt_path = output_dir / f"{stem}.pdbqt"
        self._obabel.mol_to_pdb(mol, pdb_path)
        self._obabel.pdb_to_pdbqt(pdb_path, pdbqt_path, is_receptor=False)

        return LigandPrepResult(
            name=name, smiles=smiles, mol=mol, image_path=image_path,
            pdb_path=pdb_path, pdbqt_path=pdbqt_path,
            force_field_used=ff_used, minimized_energy=energy,
        )


    def _save_2d_image(self, mol_2d: Any, path: Path, size: tuple[int, int] = (400, 400)) -> None:
        from rdkit.Chem import rdDepictor
        from rdkit.Chem.Draw import rdMolDraw2D

        rdDepictor.Compute2DCoords(mol_2d)
        try:
            drawer = rdMolDraw2D.MolDraw2DCairo(*size)
            drawer.DrawMolecule(mol_2d)
            drawer.FinishDrawing()
            path.write_bytes(drawer.GetDrawingText())
        except Exception:
            from rdkit.Chem import Draw
            img = Draw.MolToImage(mol_2d, size=size)
            img.save(str(path))

    def _strip_and_neutralize(self, mol: Any, name: str) -> Any:
        from rdkit.Chem.MolStandardize import rdMolStandardize

        result = mol
        try:
            result = rdMolStandardize.LargestFragmentChooser().choose(result)
        except Exception as exc:
            self._log.debug(f"[{name}] Salt stripping dilewati: {exc}")
        try:
            result = rdMolStandardize.Uncharger().uncharge(result)
        except Exception as exc:
            self._log.debug(f"[{name}] Netralisasi muatan dilewati: {exc}")
        return result

    def _add_hydrogens(self, mol: Any, name: str) -> Any:
        from rdkit import Chem
        try:
            return Chem.AddHs(mol, addCoords=True)
        except Exception:
            return Chem.AddHs(mol)

    def _embed_3d(self, mol: Any, name: str) -> Any:
        from rdkit.Chem import AllChem

        for params_factory in (AllChem.ETKDGv3, AllChem.ETKDGv2):
            try:
                params = params_factory()
                params.randomSeed = 42
                if AllChem.EmbedMolecule(mol, params) == 0:
                    return mol
            except Exception:
                continue
        try:
            if AllChem.EmbedMolecule(mol, randomSeed=42) == 0:
                return mol
        except Exception:
            pass
        raise ValueError(f"[{name}] Gagal melakukan embed konformasi 3D setelah semua metode dicoba.")

    def _minimize(self, mol: Any, name: str, force_field: str, max_iterations: int) -> tuple[Any, str, Optional[float]]:
        from rdkit.Chem import AllChem

        if force_field == "MMFF94":
            try:
                props = AllChem.MMFFGetMoleculeProperties(mol)
                if props is not None:
                    ff = AllChem.MMFFGetMoleculeForceField(mol, props)
                    if ff is not None:
                        ff.Minimize(maxIts=max_iterations)
                        return mol, "MMFF94", ff.CalcEnergy()
            except Exception as exc:
                self._log.debug(f"[{name}] MMFF94 gagal ({exc}), fallback ke UFF.")

        try:
            ff = AllChem.UFFGetMoleculeForceField(mol)
            if ff is not None:
                ff.Minimize(maxIts=max_iterations)
                return mol, "UFF", ff.CalcEnergy()
        except Exception as exc:
            self._log.warning(f"[{name}] Minimisasi UFF juga gagal ({exc}), memakai geometri hasil embed apa adanya.")

        return mol, "none", None

    def _compute_gasteiger(self, mol: Any, name: str) -> None:
        from rdkit.Chem import AllChem
        try:
            AllChem.ComputeGasteigerCharges(mol)
        except Exception as exc:
            self._log.warning(f"[{name}] Gagal menghitung muatan Gasteiger: {exc}")
