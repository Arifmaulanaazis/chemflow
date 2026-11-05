"""Pasangan ligan kristal dan hasil redocking untuk BIOVIA dengan koordinat asli.

Referensi memakai koordinat kristal, sedangkan hasil preparasi SMILES menjadi
masukan docking. Perubahan hanya menyangkut penomoran atom dan representasi
resonansi yang setara, tanpa translasi, rotasi, embedding, atau minimisasi.
"""
from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np


@dataclass
class RmsdPair:
    native: Any
    docked: Any
    native_indices: tuple[int, ...]
    rmsd: float

    def sdf_text(self) -> str:
        from rdkit import Chem

        stream = io.StringIO()
        writer = Chem.SDWriter(stream)
        for mol in (self.native, self.docked):
            writer.write(mol)
        writer.flush()
        text = stream.getvalue()
        writer.close()
        return text

    def write(self, directory: Path) -> dict:
        from rdkit import Chem

        directory.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, mol in (("native_crystal", self.native), ("docked", self.docked)):
            path = directory / f"{name}.sdf"
            with Chem.SDWriter(str(path)) as writer:
                writer.write(mol)
            paths[name] = path
        paths["pair"] = directory / "pair.sdf"
        paths["pair"].write_text(self.sdf_text(), encoding="utf-8")
        mapping = {"reference_source": "crystallographic_native", "alignment": "none",
                   "heavy_atoms": self.native.GetNumAtoms(), "rmsd_angstrom": self.rmsd,
                   "native_index_for_each_docked_atom": list(self.native_indices),
                   "native_name": self.native.GetProp("_Name"), "docked_name": self.docked.GetProp("_Name")}
        (directory / "atom_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        return paths


def prepare_rmsd_pair(native_pdb_block: str, docked_mol: Any, *,
                      label: str, pose_name: str, template_smiles: Optional[str] = None,
                      max_matches: int = 100000) -> RmsdPair:
    """Buat dua molekul terpisah dengan indeks atom dan graf kimia yang sama.

    CalcRMS menentukan RMSD yang memperhitungkan simetri dan resonansi.
    Kecocokan elemen serta konektivitas penuh menghasilkan pemetaan eksplisit
    yang mereproduksi nilai tersebut. Pemetaan parsial atau nilai yang berbeda
    ditolak. Jumlah kandidat dibatasi dan kegagalan tidak menghasilkan perkiraan.
    """
    from rdkit import Chem, rdBase
    from rdkit.Chem import AllChem, rdMolAlign

    raw = Chem.MolFromPDBBlock(native_pdb_block, sanitize=False, removeHs=False)
    if raw is None or docked_mol is None:
        raise ValueError("Molekul native kristal atau pose docking tidak terbaca.")
    ref, probe = Chem.RemoveHs(raw), Chem.RemoveHs(Chem.Mol(docked_mol))
    for mol in (ref, probe):
        if not mol.GetNumAtoms() or not mol.GetNumConformers():
            raise ValueError("Pasangan RMSD memerlukan atom berat dan koordinat 3D.")
        if not np.isfinite(mol.GetConformer().GetPositions()).all():
            raise ValueError("Koordinat RMSD tidak finite.")
        Chem.SanitizeMol(mol)
    if ref.GetNumAtoms() != probe.GetNumAtoms():
        raise ValueError("Jumlah atom berat native dan docked berbeda; pemetaan parsial ditolak.")
    if ref.GetNumBonds() != probe.GetNumBonds():
        raise ValueError("Konektivitas native dan docked berbeda; pemetaan parsial ditolak.")
    if template_smiles:
        template = Chem.MolFromSmiles(template_smiles)
        if template is None:
            raise ValueError("SMILES templat native tidak valid.")
        template = Chem.RemoveHs(template)
        if template.GetNumAtoms() != ref.GetNumAtoms():
            raise ValueError("Jumlah atom templat berbeda dari native kristal.")
        # Templat simetris dapat memiliki beberapa kecocokan yang sah.
        # Pemetaan eksplisit di bawah memilihnya tanpa peringatan berulang.
        with rdBase.BlockLogs():
            ref = AllChem.AssignBondOrdersFromTemplate(template, ref)
            probe = AllChem.AssignBondOrdersFromTemplate(template, probe)
    if not ref.GetSubstructMatch(probe):
        raise ValueError("Topologi penuh native dan docked tidak cocok.")

    target = float(rdMolAlign.CalcRMS(probe, ref, maxMatches=max_matches))
    params = Chem.AdjustQueryParameters.NoAdjustments()
    params.makeBondsGeneric = True
    matches = ref.GetSubstructMatches(Chem.AdjustQueryProperties(probe, params),
                                     uniquify=False, maxMatches=max_matches + 1)
    if len(matches) > max_matches:
        raise ValueError("Batas pemetaan simetri terlampaui; pasangan BIOVIA tidak diperkirakan.")
    xyz_ref, xyz_probe = ref.GetConformer().GetPositions(), probe.GetConformer().GetPositions()
    candidates = []
    for mapping in matches:
        if len(mapping) != probe.GetNumAtoms() or len(set(mapping)) != len(mapping):
            continue
        value = float(np.sqrt(np.mean(np.sum((xyz_probe - xyz_ref[list(mapping)]) ** 2, axis=1))))
        if math.isclose(value, target, abs_tol=1e-6):
            candidates.append((value, mapping))
    if not candidates:
        raise ValueError("Pemetaan atom eksplisit tidak mereproduksi CalcRMS; pasangan BIOVIA ditolak.")
    value, mapping = min(candidates, key=lambda item: (item[0], item[1]))
    # Graf kimia yang sama menyeragamkan representasi resonansi fosfat dan
    # karboksilat yang setara. Seluruh nilai koordinat asli tetap dipertahankan.
    native = Chem.Mol(probe)
    native.RemoveAllConformers()
    conformer = Chem.Conformer(probe.GetNumAtoms())
    conformer.Set3D(True)
    for i, j in enumerate(mapping):
        conformer.SetAtomPosition(i, tuple(xyz_ref[j]))
    native.AddConformer(conformer, assignId=True)
    native.SetProp("_Name", f"NATIVE_{label}_CRYSTAL")
    probe.SetProp("_Name", pose_name)
    for mol, source in ((native, "crystallographic_native"), (probe, "redocked_pose")):
        mol.SetProp("coordinate_source", source)
        mol.SetProp("alignment", "none")
    return RmsdPair(native, probe, tuple(mapping), value)
