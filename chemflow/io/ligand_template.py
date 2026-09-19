"""
SMILES ligan native dengan orde ikatan yang benar untuk redocking.

Koordinat kristal ligan pada berkas PDB tidak memuat orde ikatan, sehingga
SMILES yang diturunkan langsung dari koordinat menjadi molekul jenuh yang
salah secara kimia. Modul ini mengambil templat SMILES komponen kimia dari
RCSB (Chemical Component Dictionary) lalu menetapkan orde ikatan ke koordinat
kristal lewat ``AssignBondOrdersFromTemplate`` RDKit. Jika templat tidak bisa
diambil atau tidak cocok dengan atom yang ada, dipakai SMILES dari koordinat
sebagai cadangan.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import requests

_COMPONENT_URL = "https://data.rcsb.org/rest/v1/core/chemcomp/{code}"


def fetch_component_smiles(resname: str, cache_dir: Optional[Path] = None,
                           logger: Optional[logging.Logger] = None, timeout: float = 15.0) -> Optional[str]:
    """Ambil SMILES templat komponen kimia RCSB untuk kode residu 3 karakter.

    Hasil disimpan di ``cache_dir`` (satu file per kode) agar tidak diunduh ulang.

    Returns:
        SMILES templat, atau ``None`` bila tidak tersedia atau jaringan gagal.
    """
    log = logger or logging.getLogger(__name__)
    code = resname.strip().upper()
    if not code:
        return None

    cache_file = Path(cache_dir) / f"{code}.smi" if cache_dir else None
    if cache_file is not None and cache_file.exists():
        cached = cache_file.read_text(encoding="utf-8").strip()
        return cached or None

    try:
        response = requests.get(_COMPONENT_URL.format(code=code), timeout=timeout)
        response.raise_for_status()
        descriptor = response.json().get("rcsb_chem_comp_descriptor", {})
    except (requests.exceptions.RequestException, ValueError) as exc:
        log.warning(f"Templat komponen '{code}' tidak bisa diambil dari RCSB: {exc}")
        return None

    smiles = descriptor.get("SMILES_stereo") or descriptor.get("SMILES")
    if smiles and cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(smiles, encoding="utf-8")
    return smiles or None


def assign_bond_orders(pdb_block: str, template_smiles: str) -> Optional[Any]:
    """Tetapkan orde ikatan dari ``template_smiles`` ke koordinat pada ``pdb_block``.

    Returns:
        Mol RDKit bertopologi benar (tanpa H), atau ``None`` bila templat tidak
        cocok dengan atom berat pada blok PDB.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    template = Chem.MolFromSmiles(template_smiles)
    raw = Chem.MolFromPDBBlock(pdb_block, sanitize=False, removeHs=True)
    if template is None or raw is None:
        return None
    try:
        template = _without_explicit_hydrogens(template)
        fixed = AllChem.AssignBondOrdersFromTemplate(template, raw)
        Chem.SanitizeMol(fixed)
        return fixed
    except Exception:
        return None


def _without_explicit_hydrogens(mol: Any) -> Any:
    """Buang atom H eksplisit (templat RCSB kadang menyertakan ``[H]`` pada stereo ikatan rangkap)."""
    from rdkit import Chem

    editable = Chem.RWMol(mol)
    for idx in sorted((a.GetIdx() for a in editable.GetAtoms() if a.GetAtomicNum() == 1), reverse=True):
        editable.RemoveAtom(idx)
    cleaned = editable.GetMol()
    Chem.SanitizeMol(cleaned)
    return cleaned


def native_smiles(pdb_block: str, resname: str, cache_dir: Optional[Path] = None,
                  logger: Optional[logging.Logger] = None) -> str:
    """SMILES ligan native untuk redocking, dengan orde ikatan dari templat RCSB bila memungkinkan.

    Raises:
        ValueError: blok PDB tidak bisa diparse sama sekali.
    """
    from rdkit import Chem

    log = logger or logging.getLogger(__name__)

    template = fetch_component_smiles(resname, cache_dir=cache_dir, logger=log)
    if template:
        fixed = assign_bond_orders(pdb_block, template)
        if fixed is not None:
            return Chem.MolToSmiles(fixed)
        log.warning(f"Templat '{resname}' tidak cocok dengan atom pada struktur kristal, "
                    f"SMILES diturunkan dari koordinat (orde ikatan mungkin tidak tepat).")

    fallback = Chem.MolFromPDBBlock(pdb_block, sanitize=True, removeHs=False)
    if fallback is None:
        raise ValueError("Gagal memparse blok PDB ligan native untuk redocking.")
    return Chem.MolToSmiles(fallback)
