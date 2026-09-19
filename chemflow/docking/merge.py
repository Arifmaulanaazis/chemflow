"""
Penggabungan reseptor bersih (tanpa H, tanpa muatan) dengan pose docking
terbaik menjadi satu file PDB kompleks untuk visualisasi/analisis interaksi.

Logika inti: penamaan resName 3-karakter untuk ligan, pemilihan chain ID
ligan yang tak bentrok dengan reseptor, penggabungan conformer secara
positional (bukan lewat pencocokan substruktur), dan penyisipan TER
record pasca-tulis supaya reseptor dan ligan tampil sebagai entitas terpisah.

PENTING: reseptor yang dipakai di sini WAJIB versi
``ReceptorPreparer.prepare_for_merge()`` (tanpa H/muatan), BUKAN PDBQT
hasil ``prepare_for_docking()`` yang sudah ditambah H polar & muatan Kollman.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List, Optional

from chemflow.utils.name_sanitizer import derive_pdb_resname


def merge_complex(
    clean_receptor_mol: Any,
    best_pose_mol: Any,
    output_pdb: Path,
    *,
    ligand_name: Optional[str] = None,
    ligand_code: Optional[str] = None,
    is_native: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Path:
    """Gabungkan reseptor bersih dengan pose docking terbaik menjadi 1 PDB.

    Selain file PDB kompleks, ditulis juga sidecar JSON (nama sama, ekstensi
    ``.json``) berisi metadata identitas ligan (chain, resname, apakah ini
    kompleks referensi native), supaya modul lain (mis. analisis similaritas
    interaksi BIOVIA) bisa mengenali sisi ligan tanpa parsing ulang struktur.

    Args:
        clean_receptor_mol: RDKit Mol dari ``prepare_for_merge()``, tanpa H, tanpa muatan.
        best_pose_mol: RDKit Mol pose terbaik (mode 1) dari ``pdbqt_reader.read_pdbqt()``,
            atau (untuk referensi native) mol dari ``NativeLigand.to_pdb_block()``.
        output_pdb: path file .pdb kompleks keluaran.
        ligand_name: nama senyawa (dipakai menurunkan resName 3-karakter).
        ligand_code: kode ligan pipeline (fallback jika nama tak menghasilkan resName valid).
        is_native: True jika ``best_pose_mol`` adalah pose kristalografi asli
            ligan native (bukan hasil docking), dicatat di sidecar JSON.
        logger: logger opsional.

    Returns:
        Path file .pdb kompleks yang ditulis.

    Raises:
        RuntimeError: RDKit tidak tersedia.
        ValueError: salah satu mol input ``None``.
    """
    try:
        from rdkit import Chem
    except ImportError as exc:
        raise RuntimeError("RDKit diperlukan untuk penggabungan kompleks.") from exc

    log = logger or logging.getLogger(__name__)
    output_pdb.parent.mkdir(parents=True, exist_ok=True)

    if clean_receptor_mol is None:
        raise ValueError("clean_receptor_mol adalah None, tidak bisa menggabungkan.")
    if best_pose_mol is None:
        raise ValueError("best_pose_mol adalah None, tidak bisa menggabungkan.")

    resname = derive_pdb_resname(ligand_name or "", ligand_code or "")
    chain = _pick_ligand_chain(clean_receptor_mol)
    ligand_mol = _tag_ligand(best_pose_mol, resname=resname, chain=chain, logger=log)

    rec_mol = clean_receptor_mol
    if rec_mol.GetNumConformers() == 0:
        log.warning("Reseptor tidak punya conformer, hasil merge mungkin tidak valid.")

    combined = Chem.CombineMols(rec_mol, ligand_mol)
    complex_mol = _build_combined_conformer(rec_mol, ligand_mol, combined)

    try:
        Chem.MolToPDBFile(complex_mol, str(output_pdb))
    except Exception:
        block = Chem.MolToPDBBlock(complex_mol) or ""
        output_pdb.write_text(block, encoding="utf-8")

    _insert_ter_records(output_pdb, rec_mol.GetNumAtoms(), ligand_mol.GetNumAtoms(), logger=log)
    _write_metadata_sidecar(output_pdb, ligand_name=ligand_name, ligand_code=ligand_code,
                             ligand_chain=chain, ligand_resname=resname, is_native=is_native, logger=log)

    log.info(f"Kompleks tersimpan: {output_pdb.name} ({complex_mol.GetNumAtoms()} atom)")
    return output_pdb


def _write_metadata_sidecar(
    output_pdb: Path, *, ligand_name: Optional[str], ligand_code: Optional[str],
    ligand_chain: str, ligand_resname: str, is_native: bool, logger: logging.Logger,
) -> None:
    """Tulis sidecar JSON identitas ligan di samping file PDB kompleks."""
    metadata = {
        "ligand_name": ligand_name or "",
        "ligand_code": ligand_code or "",
        "ligand_chain": ligand_chain,
        "ligand_resname": ligand_resname,
        "is_native": is_native,
    }
    try:
        output_pdb.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning(f"Gagal menulis metadata sidecar untuk {output_pdb.name}: {exc}")


def _pick_ligand_chain(receptor_mol: Any) -> str:
    """Pilih chain ID ligan yang belum dipakai reseptor (mundur dari 'X')."""
    used = set()
    for atom in receptor_mol.GetAtoms():
        info = atom.GetPDBResidueInfo()
        if info is not None:
            cid = (info.GetChainId() or "").strip()
            if cid:
                used.add(cid)
    for candidate in "XYZWVUTSRQPONMLKJIHGFEDCBA":
        if candidate not in used:
            return candidate
    return "X"


def _tag_ligand(mol: Any, resname: str, chain: str, logger: logging.Logger) -> Any:
    from rdkit import Chem
    try:
        rw = Chem.RWMol(mol)
        for atom in rw.GetAtoms():
            info = Chem.AtomPDBResidueInfo()
            info.SetChainId(chain)
            info.SetResidueName(resname)
            info.SetResidueNumber(1)
            info.SetIsHeteroAtom(True)
            info.SetName(atom.GetSymbol() + str(atom.GetIdx() + 1))
            atom.SetPDBResidueInfo(info)
        return rw.GetMol()
    except Exception as exc:
        logger.warning(f"Penandaan PDB ligan gagal ({exc}), kompleks mungkin tak tampil sbg ligan terpisah.")
        return mol


def _build_combined_conformer(rec_mol: Any, lig_mol: Any, combined: Any) -> Any:
    from rdkit import Chem
    try:
        rec_atoms, lig_atoms = rec_mol.GetNumAtoms(), lig_mol.GetNumAtoms()
        conf = Chem.Conformer(rec_atoms + lig_atoms)

        if rec_mol.GetNumConformers() > 0:
            rc = rec_mol.GetConformer(0)
            for i in range(rec_atoms):
                conf.SetAtomPosition(i, rc.GetAtomPosition(i))
        if lig_mol.GetNumConformers() > 0:
            lc = lig_mol.GetConformer(0)
            for i in range(lig_atoms):
                conf.SetAtomPosition(rec_atoms + i, lc.GetAtomPosition(i))

        rwm = Chem.RWMol(combined)
        try:
            rwm.RemoveAllConformers()
        except Exception:
            pass
        rwm.AddConformer(conf, assignId=True)

        off = 0
        for part in (rec_mol, lig_mol):
            for i in range(part.GetNumAtoms()):
                src_info = part.GetAtomWithIdx(i).GetPDBResidueInfo()
                if src_info is not None:
                    new_info = Chem.AtomPDBResidueInfo()
                    new_info.SetChainId(src_info.GetChainId())
                    new_info.SetResidueName(src_info.GetResidueName())
                    new_info.SetResidueNumber(src_info.GetResidueNumber())
                    new_info.SetIsHeteroAtom(src_info.GetIsHeteroAtom())
                    new_info.SetName(src_info.GetName())
                    rwm.GetAtomWithIdx(off + i).SetPDBResidueInfo(new_info)
            off += part.GetNumAtoms()

        return rwm.GetMol()
    except Exception:
        return combined


def _insert_ter_records(output_pdb: Path, n_receptor_atoms: int, n_ligand_atoms: int,
                         logger: logging.Logger) -> None:
    """Sisipkan TER setelah blok reseptor & ligan (post-processing teks,
    positional; no-op jika jumlah atom tak sesuai ekspektasi, supaya tidak
    merusak file yang secara struktur sudah valid)."""
    try:
        lines = output_pdb.read_text(encoding="utf-8").splitlines(keepends=True)
        atom_idx = [i for i, line in enumerate(lines) if line.startswith(("ATOM", "HETATM"))]
        if len(atom_idx) != n_receptor_atoms + n_ligand_atoms:
            return

        last_receptor_line = atom_idx[n_receptor_atoms - 1] if n_receptor_atoms else None
        last_ligand_line = atom_idx[-1]

        out: List[str] = []
        for i, line in enumerate(lines):
            if line.startswith(("END", "MASTER")):
                continue
            out.append(line)
            if i == last_receptor_line or i == last_ligand_line:
                out.append("TER\n")
        out.append("END\n")
        output_pdb.write_text("".join(out), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Gagal menyisipkan TER record ke {output_pdb.name}: {exc}")
