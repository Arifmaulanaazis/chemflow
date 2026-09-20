"""
Checkpoint per item untuk ``chemflow resume``: ligan siap docking dan reseptor
siap docking (termasuk gridbox dan ligan native yang sudah dipilih).

Setiap checkpoint adalah JSON kecil di samping artefaknya (``prepared.json``),
ditulis atomik oleh ``state.write_json_atomic``. Path disimpan relatif terhadap
folder output supaya folder boleh dipindah. Checkpoint dianggap sah hanya bila
file artefak yang dirujuknya masih ada.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from chemflow.chem.ligand_preparer import LigandPrepResult
from chemflow.docking.docking_matrix import ReceptorDockingTarget
from chemflow.docking.grid_box import GridBox
from chemflow.io.pdb_fetcher import NativeLigand
from chemflow.state import from_rel, read_json, to_rel, write_json_atomic

PREPARED_FILENAME = "prepared.json"


def _nonempty(path: Optional[Path]) -> bool:
    try:
        return path is not None and path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def save_ligand_prep(directory: Path, result: LigandPrepResult, lipinski: Optional[Dict[str, Any]],
                     base: Path) -> None:
    """Simpan ringkasan preparasi satu ligan (dan baris Lipinski-nya) sebagai checkpoint."""
    write_json_atomic(directory / PREPARED_FILENAME, {
        "name": result.name, "smiles": result.smiles,
        "force_field_used": result.force_field_used, "minimized_energy": result.minimized_energy,
        "image": to_rel(result.image_path, base), "pdb": to_rel(result.pdb_path, base),
        "pdbqt": to_rel(result.pdbqt_path, base), "lipinski": lipinski,
    })


def load_ligand_prep(
    directory: Path, base: Path, expected_smiles: Optional[str] = None,
) -> Optional[Tuple[LigandPrepResult, Optional[Dict[str, Any]]]]:
    """Muat checkpoint ligan; ``None`` bila tak ada, rusak, SMILES berubah, atau berkas hilang.

    ``LigandPrepResult.mol`` bernilai ``None`` pada hasil muat (baris Lipinski sudah tersimpan).
    """
    data = read_json(directory / PREPARED_FILENAME)
    if not data:
        return None
    try:
        smiles = data["smiles"]
        if expected_smiles is not None and smiles != expected_smiles:
            return None
        pdb, pdbqt = from_rel(data["pdb"], base), from_rel(data["pdbqt"], base)
        if not (_nonempty(pdb) and _nonempty(pdbqt)):
            return None
        image = from_rel(data.get("image"), base)
        result = LigandPrepResult(
            name=data["name"], smiles=smiles, mol=None,
            image_path=image if _nonempty(image) else None, pdb_path=pdb, pdbqt_path=pdbqt,
            force_field_used=data.get("force_field_used", "none"),
            minimized_energy=data.get("minimized_energy"),
        )
    except (KeyError, TypeError):
        return None
    return result, data.get("lipinski")


def save_receptor(directory: Path, target: ReceptorDockingTarget, native: Optional[NativeLigand],
                  base: Path) -> None:
    """Simpan reseptor siap docking beserta gridbox dan ligan native pilihan (tanpa prompt ulang saat resume)."""
    write_json_atomic(directory / PREPARED_FILENAME, {
        "key": target.key, "pdb_code": target.pdb_code,
        "receptor_pdbqt": to_rel(target.receptor_pdbqt, base),
        "receptor_clean_pdb": to_rel(target.receptor_clean_pdb, base),
        "grid_box": asdict(target.grid_box),
        "native": asdict(native) if native is not None else None,
    })


def load_receptor(
    directory: Path, base: Path,
) -> Optional[Tuple[ReceptorDockingTarget, Optional[NativeLigand]]]:
    """Muat checkpoint reseptor; ``None`` bila tak ada, rusak, atau berkas PDBQT/PDB bersih hilang."""
    data = read_json(directory / PREPARED_FILENAME)
    if not data:
        return None
    try:
        pdbqt, clean = from_rel(data["receptor_pdbqt"], base), from_rel(data["receptor_clean_pdb"], base)
        if not (_nonempty(pdbqt) and _nonempty(clean)):
            return None
        target = ReceptorDockingTarget(
            key=data["key"], pdb_code=data["pdb_code"], receptor_pdbqt=pdbqt, receptor_clean_pdb=clean,
            grid_box=GridBox(**data["grid_box"]),
        )
        raw_native = data.get("native")
        native = NativeLigand(**raw_native) if raw_native else None
    except (KeyError, TypeError):
        return None
    return target, native
