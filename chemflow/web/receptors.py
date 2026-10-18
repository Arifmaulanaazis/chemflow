"""Padanan receptor-config di browser: pemilihan ligan native atau koordinat eksplisit."""
from __future__ import annotations
import math
import re
import json
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from chemflow.io.pdb_fetcher import fetch_pdb
from chemflow.io.receptor_config import ReceptorConfigRow, suggest_box_size, write_receptor_config


class ReceptorRow(BaseModel):
    pdb_code: str = Field(pattern=r"^[0-9][A-Za-z0-9]{3}$")
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    native_ligand: str = Field(default="manual", max_length=50, pattern=r"^[\w -]+$")

    @field_validator("center", "size")
    @classmethod
    def finite(cls, values, info):
        if not all(math.isfinite(v) and abs(v) < 100000 for v in values):
            raise ValueError("Koordinat harus berupa angka terbatas.")
        if info.field_name == "size" and not all(0 < v <= 200 for v in values):
            raise ValueError("Ukuran kotak harus > 0 dan <= 200 Angstrom.")
        return values


class ReceptorWorkbook(BaseModel):
    rows: list[ReceptorRow] = Field(min_length=1, max_length=100)


def router(workspace: Path):
    routes = APIRouter(prefix="/api/receptors")

    @routes.get("/{pdb_code}")
    def inspect(pdb_code: str):
        if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", pdb_code):
            raise HTTPException(422, "Kode PDB terdiri dari angka diikuti tiga huruf/angka.")
        try:
            receptor = fetch_pdb(pdb_code, workspace / "receptor-cache")
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"pdb_code": receptor.pdb_code, "ligands": [{"label": l.label, "chain": l.chain, "residue": l.resname,
                "resnum": l.resnum, "selection": f"{l.resnum}"+(f":{l.chain}" if l.chain.strip() else "")+" and hetero",
                "atoms": l.atom_count, "center": [l.center_x, l.center_y, l.center_z], "size": [suggest_box_size(l)] * 3} for l in receptor.native_ligands]}

    @routes.get("/{pdb_code}/structure")
    def structure(pdb_code: str):
        if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", pdb_code):
            raise HTTPException(422,"Kode PDB tidak valid.")
        try: receptor=fetch_pdb(pdb_code,workspace/"receptor-cache")
        except RuntimeError as exc: raise HTTPException(502,str(exc)) from exc
        return FileResponse(receptor.pdb_path,media_type="chemical/x-pdb",headers={"Cache-Control":"private, max-age=3600"})

    @routes.post("")
    def workbook(body: ReceptorWorkbook):
        upload_id = uuid.uuid4().hex
        path = workspace / "uploads" / upload_id / "reseptor.xlsx"
        rows = [ReceptorConfigRow(r.pdb_code.upper(), r.center, r.size, r.native_ligand) for r in body.rows]
        write_receptor_config(rows, path)
        path.with_name(".metadata.json").write_text(json.dumps({"purpose": "receptors"}), encoding="utf-8")
        return {"id": upload_id + "/reseptor.xlsx", "name": path.name, "size": path.stat().st_size, "purpose": "receptors"}

    return routes
