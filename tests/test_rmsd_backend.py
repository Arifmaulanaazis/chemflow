import io
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from chemflow.docking.rmsd_backend import RmsdBackendSession
from chemflow.docking.rmsd_pair import prepare_rmsd_pair
from chemflow.docking.rmsd_validation import RedockingValidator
from chemflow.interaction.biovia_gui import BioviaError
from chemflow.interaction.biovia_rmsd import (
    BioviaRmsdClient, BioviaRmsdMeasurement, build_rmsd_script, read_rmsd_result,
)


def molecules(smiles="CCO", shift=(0., 0., 0.)):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    mol = Chem.RemoveHs(mol)
    block = Chem.MolToPDBBlock(mol)
    # Gunakan koordinat PDB yang dibulatkan untuk kedua molekul agar presisinya sama.
    native = Chem.MolFromPDBBlock(block)
    pose = Chem.Mol(native)
    coords = native.GetConformer().GetPositions() + np.asarray(shift)
    for i, xyz in enumerate(coords):
        pose.GetConformer().SetAtomPosition(i, tuple(xyz))
    return block, native, pose


def pair_for_test(shift=(.5, 0., 0.)):
    block, native, pose = molecules(shift=shift)
    return prepare_rmsd_pair(block, pose, label="ETH_A1", pose_name="ETH_rep01_mode01", template_smiles="CCO")


def test_pair_keeps_crystal_and_pose_coordinates_and_roundtrips(tmp_path):
    block, native, pose = molecules(shift=(10., -5., 3.))
    before = pose.GetConformer().GetPositions().copy()
    pair = prepare_rmsd_pair(block, pose, label="ETH_A1", pose_name="mode1", template_smiles="CCO")
    assert pair.rmsd == pytest.approx(math.sqrt(134), abs=1e-6)
    assert np.array_equal(pose.GetConformer().GetPositions(), before)
    assert np.array_equal(pair.docked.GetConformer().GetPositions(), before)
    assert np.array_equal(pair.native.GetConformer().GetPositions(),
                          native.GetConformer().GetPositions()[list(pair.native_indices)])
    paths = pair.write(tmp_path)
    records = list(Chem.ForwardSDMolSupplier(io.BytesIO(paths["pair"].read_bytes())))
    assert len(records) == 2 and [m.GetNumAtoms() for m in records] == [3, 3]
    assert records[0].GetProp("coordinate_source") == "crystallographic_native"
    raw = np.sqrt(np.mean(np.sum((records[0].GetConformer().GetPositions() -
                                 records[1].GetConformer().GetPositions()) ** 2, axis=1)))
    assert raw == pytest.approx(pair.rmsd, abs=1e-4)


def test_pair_handles_reordered_atoms():
    block, native, pose = molecules()
    reordered = Chem.RenumberAtoms(pose, [2, 0, 1])
    pair = prepare_rmsd_pair(block, reordered, label="ETH", pose_name="pose", template_smiles="CCO")
    assert pair.rmsd < 1e-6
    assert pair.native_indices == (2, 0, 1)


def test_pair_rejects_partial_and_different_graphs():
    block, _, pose = molecules()
    _, _, different = molecules("CCCO")
    with pytest.raises(ValueError, match="Jumlah atom berat"):
        prepare_rmsd_pair(block, different, label="X", pose_name="X")
    broken = Chem.RWMol(pose)
    broken.RemoveBond(0, 1)
    with pytest.raises((ValueError, RuntimeError)):
        prepare_rmsd_pair(block, broken.GetMol(), label="X", pose_name="X", template_smiles="CCO")


def test_pair_handles_resonance_equivalent_phosphate_oxygen():
    block, _, pose = molecules("OP(=O)(O)O")
    # Tukar posisi oksigen terminal berikatan rangkap dan oksigen berikatan tunggal.
    conf = pose.GetConformer()
    a, b = tuple(conf.GetAtomPosition(2)), tuple(conf.GetAtomPosition(3))
    conf.SetAtomPosition(2, b)
    conf.SetAtomPosition(3, a)
    pair = prepare_rmsd_pair(block, pose, label="PO4", pose_name="mode1", template_smiles="OP(=O)(O)O")
    assert pair.rmsd < 1e-6
    assert np.array_equal(pair.native.GetConformer().GetPositions(), pair.docked.GetConformer().GetPositions())


def test_script_uses_biovia_compute_and_native_export_without_alignment(tmp_path):
    script = build_rmsd_script(pair_for_test(), "abc", tmp_path / "result's.tsv", tmp_path / "overlay.png")
    assert "CalculateHeavyAtomRmsd($native, $docked)" in script
    assert script.count("->CreateMolecule()") == 2
    assert "->SaveImage(" in script and "->Close()" in script
    assert script.count("->CreateScreenLabel(") == 3
    assert "Sebelum redocking: native kristal" in script
    assert "Sesudah redocking: pose hasil docking" in script
    assert "result\\'s.tsv" in script
    assert not any(word in script for word in ("Superimpose", "->Clean(", "->Translate(", "->Rotate("))
    assert "->SaveImage(" not in build_rmsd_script(pair_for_test(), "abc", tmp_path / "r.tsv")


@pytest.mark.parametrize("text", ["old\t0.5\t\t\n", "abc\t0.5\t\t", ""])
def test_report_rejects_stale_or_partial_result(tmp_path, text):
    path = tmp_path / "r.tsv"
    path.write_text(text)
    assert read_rmsd_result(path, "abc", .5) is None


@pytest.mark.parametrize("text", ["abc\tnan\t\t\n", "abc\tinf\t\t\n", "abc\t-1\t\t\n",
                                  "abc\t0.1\t\t\n", "abc\t\tbad graph\t\n"])
def test_report_rejects_invalid_and_inconsistent_values(tmp_path, text):
    path = tmp_path / "r.tsv"
    path.write_text(text)
    with pytest.raises(BioviaError):
        read_rmsd_result(path, "abc", .5)


def test_report_keeps_scalar_when_only_visualization_fails(tmp_path):
    path = tmp_path / "r.tsv"
    path.write_text("abc\t0.5\t\tPNG unavailable\n")
    assert read_rmsd_result(path, "abc", .5) == (.5, "PNG unavailable")


def config(tmp_path, backend="auto"):
    return SimpleNamespace(output_dir=tmp_path, rmsd_backend=backend, biovia_exe=None,
                           biovia_launch_timeout=5, lock_input=False, rmsd_overlay=True)


def enhance(session, tmp_path, name="pose"):
    block, _, pose = molecules(shift=(.5, 0., 0.))
    result = session.validator.validate(block, pose, "ETH")
    return session.enhance(result, block, pose, "ETH", template_smiles="CCO",
                           directory=tmp_path / "rmsd" / name, pose_name=name)


def test_absent_biovia_falls_back_once_and_still_saves_pair(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("chemflow.docking.rmsd_backend.detect_biovia", lambda *_: calls.append(1))
    with RmsdBackendSession(config(tmp_path), RedockingValidator()) as session:
        for name in ("a", "b"):
            result, details = enhance(session, tmp_path, name)
            assert result.method == "CalcRMS" and result.rmsd == .5
            assert details["rmsd_backend"] == "rdkit" and details["fallback_reason"]
            assert (tmp_path / details["rmsd_pair"]).is_file()
            assert details["rmsd_overlay"] == ""
    assert calls == [1]


def test_explicit_rdkit_never_detects_or_launches_gui(tmp_path, monkeypatch):
    monkeypatch.setattr("chemflow.docking.rmsd_backend.detect_biovia",
                        lambda *_: pytest.fail("RDKit backend touched BIOVIA"))
    with RmsdBackendSession(config(tmp_path, "rdkit"), RedockingValidator()) as session:
        result, details = enhance(session, tmp_path)
    assert result.method == "CalcRMS" and details["fallback_reason"] == ""


def test_detection_error_also_falls_back(tmp_path, monkeypatch):
    def inaccessible(*args):
        raise PermissionError("registry unavailable")

    monkeypatch.setattr("chemflow.docking.rmsd_backend.detect_biovia", inaccessible)
    with RmsdBackendSession(config(tmp_path), RedockingValidator()) as session:
        result, details = enhance(session, tmp_path)
    assert result.method == "CalcRMS" and "registry unavailable" in details["fallback_reason"]


@pytest.mark.parametrize("failure", [None, "prepare", "calculate"])
def test_biovia_session_success_and_runtime_failure_cleanup(tmp_path, monkeypatch, failure):
    calls = []

    class Client:
        def __init__(self, *a, **kw): pass
        def prepare(self):
            calls.append("prepare")
            if failure == "prepare": raise RuntimeError("license unavailable")
        def calculate_rmsd(self, pair, directory, **kw):
            calls.append("calculate")
            if failure == "calculate": raise RuntimeError("GUI unavailable")
            return BioviaRmsdMeasurement(pair.rmsd, "clipboard", directory / "report.tsv")
        def recover(self): calls.append("recover")
        def close(self): calls.append("close")

    monkeypatch.setattr("chemflow.docking.rmsd_backend.detect_biovia", lambda *_: Path("BIOVIA.exe"))
    monkeypatch.setattr("chemflow.interaction.biovia_rmsd.BioviaRmsdClient", Client)
    with RmsdBackendSession(config(tmp_path), RedockingValidator()) as session:
        result, details = enhance(session, tmp_path)
        second, _ = enhance(session, tmp_path, "second")
    assert calls.count("prepare") == 1 and calls.count("close") == 1
    if failure:
        assert result.method == second.method == "CalcRMS"
        assert details["fallback_reason"] and calls.count("calculate") <= 1
    else:
        assert result.method == second.method == "BIOVIA_HeavyAtoms"
        assert details["rmsd_transport"] == "clipboard"


def test_clipboard_failure_runs_one_script_file_and_checks_fresh_result(tmp_path, monkeypatch):
    client = object.__new__(BioviaRmsdClient)
    client._lock = SimpleNamespace(pulse=lambda: None)
    client._log = SimpleNamespace(info=lambda *_: None)
    client.recover = lambda: None
    client._paste_script = lambda _: (_ for _ in ()).throw(RuntimeError("clipboard unavailable"))
    captured = []

    def execute(path):
        import re
        script = path.read_text()
        token = re.search(r"print \$out '([a-f0-9]+)'", script).group(1)
        captured.append(path)
        (path.parent / "biovia_result.tsv").write_text(f"{token}\t0.5\t\t\n")

    client._execute_script_file = execute
    result = client.calculate_rmsd(pair_for_test(), tmp_path, save_overlay=False, timeout=.1)
    assert result.transport == "script_file" and result.rmsd == pytest.approx(.5)
    assert len(captured) == 1


def test_rmsd_defaults_and_optouts():
    from chemflow.cli import build_parser

    args = build_parser().parse_args(["run", "--receptors", "r.xlsx"])
    assert args.run_rmsd_validation and args.rmsd_backend == "auto" and args.rmsd_overlay
    args = build_parser().parse_args(["run", "--receptors", "r.xlsx", "--no-run-rmsd-validation",
                                      "--rmsd-backend", "rdkit", "--no-rmsd-overlay"])
    assert not args.run_rmsd_validation and not args.rmsd_overlay and args.rmsd_backend == "rdkit"


def test_qt_unnamed_popup_menu_is_found_without_touching_other_apps():
    client = object.__new__(BioviaRmsdClient)
    client._hwnd = 10
    client._control = lambda **kw: None
    client._top_windows = lambda: [(10, "Discovery Studio", "QtMain"), (20, "", "QtPopup")]
    control = object()
    spec = SimpleNamespace(exists=lambda **kw: True, wrapper_object=lambda: control)
    popup = SimpleNamespace(child_window=lambda **kw: spec)
    app = SimpleNamespace(connect=lambda **kw: SimpleNamespace(window=lambda **kw: popup))
    client._rt = SimpleNamespace(Application=lambda **kw: app)
    assert client._menu_control("Run") is control


def test_clipboard_script_targets_only_the_new_owned_editor():
    client = object.__new__(BioviaRmsdClient)
    state = {"new": False, "clipboard": "user text", "clicked": [], "ran": []}
    script = "use strict;\nprint 'test';\n"
    old_editor = SimpleNamespace(element_info=SimpleNamespace(runtime_id=(1,)))
    new_editor = SimpleNamespace(element_info=SimpleNamespace(runtime_id=(2,)))
    tab = SimpleNamespace(window_text=lambda: "Script (1)")
    old_tab = SimpleNamespace(window_text=lambda: "Script")
    client._window = SimpleNamespace(descendants=lambda **kw: [old_tab, tab] if state["new"] else [old_tab])
    client._script_editors = lambda: [old_editor, new_editor] if state["new"] else [old_editor]
    client._menu = lambda *a: state.update(new=True)
    client._tab = lambda fn: tab if fn("Script (1)") else None
    client._opened = {}
    client._click = lambda c: state["clicked"].append(c)
    client._run_script_editor = lambda c: state["ran"].append(c)
    client._rt = SimpleNamespace(pyperclip=SimpleNamespace(
        paste=lambda: state["clipboard"], copy=lambda text: state.update(clipboard=text)))
    client._keys = lambda keys: None
    client._wait = lambda condition, *a, **kw: condition() or pytest.fail("condition failed")
    assert client._paste_script(script) == "Script (1)"
    assert state["clicked"] == state["ran"] == [new_editor]
    assert state["clipboard"] == "user text"
    assert client._opened == {"Script (1)": ("Script (1)", None)}


def test_user_cancellation_is_not_converted_to_rdkit_fallback(tmp_path, monkeypatch):
    calls = []

    class Client:
        def __init__(self, *a, **kw): pass
        def prepare(self): pass
        def calculate_rmsd(self, *a, **kw): raise KeyboardInterrupt
        def close(self): calls.append("close")
        def recover(self): pytest.fail("Cancellation must propagate")

    monkeypatch.setattr("chemflow.docking.rmsd_backend.detect_biovia", lambda *_: Path("BIOVIA.exe"))
    monkeypatch.setattr("chemflow.interaction.biovia_rmsd.BioviaRmsdClient", Client)
    with pytest.raises(KeyboardInterrupt):
        with RmsdBackendSession(config(tmp_path), RedockingValidator()) as session:
            enhance(session, tmp_path)
    assert calls == ["close"]
