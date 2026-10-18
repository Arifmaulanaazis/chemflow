"""Pilihan executable didaftarkan oleh server, tidak pernah diunggah dari browser."""
import hashlib
import os
import shutil
from pathlib import Path
from fastapi import HTTPException

TOOL_OPTIONS = {
    "vina_executable": ("Vina", "vina", "CHEMFLOW_WEB_VINA_EXECUTABLE"),
    "openbabel_path": ("OpenBabel", "obabel", "CHEMFLOW_WEB_OPENBABEL_PATH"),
    "biovia_exe": ("BIOVIA", None, "CHEMFLOW_WEB_BIOVIA_EXE"),
}


def registered_tools(name):
    label, binary, variable = TOOL_OPTIONS[name]
    candidates = [os.environ.get(variable), shutil.which(binary) if binary else None]
    found = {}
    for value in candidates:
        if not value:
            continue
        path = Path(value).expanduser().resolve()
        if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
            key = hashlib.sha256(str(path).encode()).hexdigest()[:24]
            found[key] = {"id": key, "label": f"{label}: {path.name} ({path.parent})", "path": str(path)}
    return list(found.values())


def resolve_tool(name, value):
    for tool in registered_tools(name):
        if tool["id"] == value:
            return tool["path"]
    raise HTTPException(422, "Executable harus dipilih dari instalasi yang didaftarkan server.")
