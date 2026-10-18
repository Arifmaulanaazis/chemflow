"""Input browser terstruktur untuk proses anak CLI; perilaku TTY biasa tidak berubah."""
from __future__ import annotations
import json
import os
import time
import uuid
from pathlib import Path


def enabled():
    return bool(os.environ.get("CHEMFLOW_PROMPT_DIR"))


def request(kind, title, **context):
    folder = Path(os.environ["CHEMFLOW_PROMPT_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    payload = {"id": token, "kind": kind, "title": title, "created": time.time(), **context}
    temporary = folder / f"{token}.tmp"
    target = folder / f"{token}.request.json"
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(target)
    print(f"[WebUI] Menunggu input: {title}", flush=True)
    response = folder / f"{token}.response.json"
    try:
        # Job yang dibatalkan menghentikan proses anak ini. Timeout mencegah job
        # terbengkalai memblokir antrean serial tanpa batas.
        deadline = time.monotonic() + 24 * 3600
        while time.monotonic() < deadline:
            if response.exists():
                return json.loads(response.read_text(encoding="utf-8"))
            time.sleep(.25)
        raise RuntimeError("Input browser tidak dijawab dalam 24 jam; lanjutkan dari checkpoint.")
    finally:
        target.unlink(missing_ok=True)
        response.unlink(missing_ok=True)


def native_gridbox(receptor, default_size, padding):
    from chemflow.docking.grid_box import GridBox
    ligands = receptor.native_ligands
    choices = [{"label": l.label, "atoms": l.atom_count,
                "center": [l.center_x, l.center_y, l.center_z],
                "size": [GridBox.suggested_size(l.extent, padding)] * 3} for l in ligands]
    answer = request("gridbox", f"Tentukan situs docking {receptor.pdb_code}",
                     pdb_code=receptor.pdb_code, choices=choices, default_size=list(default_size))
    native = next((l for l in ligands if l.label == answer.get("native")), None)
    return (*answer["center"], *answer["size"], native)
