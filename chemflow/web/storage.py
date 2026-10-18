"""Path workspace terbatas dan pratinjau artefak yang berbatas serta inert."""
from __future__ import annotations
import csv
import math
import zipfile
from pathlib import Path
from fastapi import HTTPException
UPLOAD_EXTENSIONS = {".xlsx", ".xls", ".csv", ".tsv", ".txt", ".pdb", ".pdbqt", ".sdf", ".mol", ".mol2", ".cdf", ".mzml", ".mzxml", ".json"}
MAX_UPLOAD = 100 * 1024 * 1024
MAX_PREVIEW = 20 * 1024 * 1024


def confined(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise HTTPException(400, "Path di luar workspace tidak diizinkan.")
    return target


def artifacts(root: Path) -> list[dict]:
    if not root.exists():
        return []
    result = []
    for path in sorted(root.rglob("*")):
        if len(result) >= 5000:
            break
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):
            stat = path.stat()
            result.append({"path": path.relative_to(root).as_posix(), "size": stat.st_size, "modified": stat.st_mtime, "extension": path.suffix.lower()})
    return result


def clean_cell(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if isinstance(value, (str, int, float, bool, type(None))) else str(value)


def preview(path: Path, sheet: str | None = None) -> dict:
    if path.stat().st_size > MAX_PREVIEW:
        raise HTTPException(413, "Preview dibatasi 20 MB. Unduh berkas untuk membuka seluruhnya.")
    ext = path.suffix.lower()
    if ext == ".xlsx":
        from openpyxl import load_workbook
        try:
            with zipfile.ZipFile(path) as archive:
                if sum(x.file_size for x in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValueError("Workbook terkompresi terlalu besar")
            wb = load_workbook(path, read_only=True, data_only=True)
            try:
                ws = wb[sheet] if sheet else wb.active
                rows = [[clean_cell(v) for v in row] for row in ws.iter_rows(max_row=202, max_col=min(ws.max_column or 60, 60), values_only=True)]
                return {"kind": "table", "sheets": wb.sheetnames, "sheet": ws.title, "rows": rows[:201], "truncated": len(rows) > 201 or (ws.max_column or 0) > 60}
            finally:
                wb.close()
        except (ValueError, KeyError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, str(exc)) from exc
    if ext in {".csv", ".tsv"}:
        import itertools
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            rows = list(itertools.islice(csv.reader(stream, delimiter="\t" if ext == ".tsv" else ","), 202))
        return {"kind": "table", "rows": [r[:60] for r in rows[:201]], "truncated": len(rows) > 201 or any(len(r) > 60 for r in rows)}
    if ext in {".json", ".log", ".txt", ".pdb", ".pdbqt", ".sdf", ".mol", ".mol2", ".svg"}:
        with path.open(encoding="utf-8", errors="replace") as stream:
            text = stream.read(100001)
        return {"kind": "text", "text": text[:100000], "truncated": len(text) > 100000}
    return {"kind": "download"}


def docking_gridbox(root: Path, relative: str) -> dict:
    import json
    parts = Path(relative).parts
    prefixes = (("receptors",), ("docking",), ("complexes",),
                ("rmsd", "complexes"), ("rmsd", "interaction_source", "complexes"))
    for prefix in prefixes:
        if parts[:len(prefix)] != prefix or len(parts) <= len(prefix) + 1:
            continue
        key = parts[len(prefix)]
        checkpoint = confined(root, f"receptors/{key}/prepared.json")
        try:
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            box = data["grid_box"]
            coordinates = [float(box[f"{kind}_{axis}"]) for kind in ("center", "size") for axis in "xyz"]
            if not all(math.isfinite(v) for v in coordinates) or any(v <= 0 for v in coordinates[3:]):
                break
            return {"coordinates": coordinates, "receptor": key}
        except (OSError, ValueError, KeyError, TypeError):
            break
    return {"coordinates": None, "receptor": None}
