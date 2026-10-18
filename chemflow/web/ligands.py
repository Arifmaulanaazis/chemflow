"""Input ligan bertipe diubah menjadi workbook yang sama dengan yang dibaca CLI."""
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class LigandRow(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    smiles: str = Field(default="", max_length=10000)
    group: str = Field(default="", max_length=200)


class LigandWorkbook(BaseModel):
    rows: list[LigandRow] = Field(min_length=1, max_length=1000)


def router(workspace: Path):
    routes = APIRouter(prefix="/api/ligands")

    @routes.post("")
    def workbook(body: LigandWorkbook):
        from rdkit import Chem
        from openpyxl import Workbook
        for i, row in enumerate(body.rows, 1):
            if not row.name.strip():
                raise HTTPException(422, f"Baris {i}: isi nama senyawa.")
            if row.smiles.strip() and Chem.MolFromSmiles(row.smiles.strip()) is None:
                raise HTTPException(422, f"Baris {i}: SMILES tidak valid.")
        upload_id = uuid.uuid4().hex
        path = workspace / "uploads" / upload_id / "ligan.xlsx"
        path.parent.mkdir(parents=True)
        wb = Workbook(); sheet = wb.active; sheet.title = "Ligan"
        sheet.append(["name", "smiles", "group"])
        for row in body.rows:
            # Tipe teks eksplisit mencegah injeksi rumus spreadsheet.
            sheet.append([row.name.strip(), row.smiles.strip(), row.group.strip()])
            for cell in sheet[sheet.max_row]:
                cell.data_type = "s"
        wb.save(path)
        return {"id": upload_id + "/ligan.xlsx", "name": path.name, "size": path.stat().st_size}
    return routes
