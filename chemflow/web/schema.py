"""Tampilkan opsi argparse tanpa menggandakan pengaturan ilmiah CLI."""
from __future__ import annotations
import argparse
import math
from pathlib import Path
from fastapi import HTTPException
from .tools import TOOL_OPTIONS, registered_tools, resolve_tool

COMMANDS = ("init", "run", "resume", "similarity", "gcms", "interactions")
BLOCKED = {"output", "no_progress", "admet_ssl_verify"}


def parsers():
    from chemflow.cli import build_parser
    parser = build_parser()
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices


def schema() -> dict:
    result = {}
    for command, parser in parsers().items():
        if command not in COMMANDS:
            continue
        options = []
        for group in parser._action_groups:
            for a in group._group_actions:
                if a.dest in BLOCKED or a.dest == "help":
                    continue
                boolean = isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse.BooleanOptionalAction))
                options.append({"name": a.dest, "flag": a.option_strings[0], "label": a.option_strings[0][2:].replace("-", " "), "group": group.title,
                                "help": a.help or "", "required": a.required,
                                "kind": "tool" if a.dest in TOOL_OPTIONS else "boolean" if boolean else "file" if a.type is Path else "number" if a.type in (int, float) else "text",
                                "multiple": a.nargs in ("+", "*") or isinstance(a.nargs, int),
                                "count": a.nargs if isinstance(a.nargs, int) else None,
                                "tool_choices": [{"id": t["id"], "label": t["label"]} for t in registered_tools(a.dest)] if a.dest in TOOL_OPTIONS else None,
                                "choices": a.choices, "default": str(a.default) if isinstance(a.default, Path) else a.default})
        result[command] = options
    return result


def build_arguments(command: str, options: dict, output: Path, resolve_input) -> list[str]:
    if command not in COMMANDS:
        raise HTTPException(422, "Perintah tidak tersedia di WebUI.")
    actions = {a.dest: a for a in parsers()[command]._actions if a.dest not in BLOCKED and a.dest != "help"}
    if set(options) - actions.keys():
        raise HTTPException(422, "Opsi tidak dikenal atau hanya boleh dikonfigurasi oleh operator server.")
    argv = [command, "--output", str(output)]
    for name, value in options.items():
        if value is None or value == "":
            continue
        a = actions[name]
        if isinstance(a, argparse.BooleanOptionalAction):
            if not isinstance(value, bool):
                raise HTTPException(422, f"{name}: gunakan boolean.")
            argv.append(a.option_strings[0] if value else a.option_strings[1])
        elif isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            if not isinstance(value, bool):
                raise HTTPException(422, f"{name}: gunakan boolean.")
            if value:
                argv.append(a.option_strings[0])
        else:
            multiple = a.nargs in ("+", "*") or isinstance(a.nargs, int)
            values = value if multiple and isinstance(value, list) else [value]
            if multiple and not values:
                continue
            if len(values) > 100 or (isinstance(a.nargs, int) and len(values) != a.nargs):
                raise HTTPException(422, f"{name}: jumlah nilai tidak valid.")
            argv.append(a.option_strings[0])
            for item in values:
                text = str(item)
                if len(text) > 1000 or text.startswith("-") and a.type not in (int, float):
                    raise HTTPException(422, f"{name}: nilai tidak valid.")
                if name in TOOL_OPTIONS:
                    text = resolve_tool(name, text)
                elif a.type is Path:
                    text = str(resolve_input(text))
                if a.type in (int, float):
                    try:
                        number = a.type(text)
                        if not math.isfinite(number) or abs(number) > 1000000:
                            raise ValueError()
                    except ValueError:
                        raise HTTPException(422, f"{name}: angka tidak valid.")
                if a.choices and (a.type(text) if a.type else text) not in a.choices:
                    raise HTTPException(422, f"{name}: pilihan tidak valid.")
                if name in {"result_filename", "interaction_suffix"} and (Path(text).name != text or ":" in text or "\\" in text or "/" in text):
                    raise HTTPException(422, "Nama berkas harus tanpa folder.")
                argv.append(text)
    if command == "run":
        if not options.get("receptors") or (not options.get("rmsd_only") and not options.get("ligands")):
            raise HTTPException(422, "Unggah reseptor dan ligan (kecuali validasi RMSD saja).")
        argv += ["--admet-ssl-verify"]
    if command == "resume":
        argv += ["--admet-ssl-verify"]
    if any(a.dest == "no_progress" for a in parsers()[command]._actions):
        argv.append("--no-progress")
    return argv
