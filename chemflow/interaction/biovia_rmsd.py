"""Perhitungan RMSD melalui API DiscoveryScript resmi BIOVIA.

Script yang ditempel lewat clipboard membentuk dua molekul di memori.
Cadangannya menjalankan satu berkas script. BIOVIA menghitung nilai RMSD dan
mengekspor tampilan molekul langsung, sehingga jendela aplikasi lain tidak
menutupi gambar hasilnya.
"""
from __future__ import annotations

import math
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from chemflow.docking.rmsd_pair import RmsdPair
from chemflow.interaction.biovia_gui import BioviaClient, BioviaError


def _perl_string(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_rmsd_script(pair: RmsdPair, token: str, result_path: Path,
                      overlay_path: Optional[Path] = None) -> str:
    """Buat molekul BIOVIA dengan urutan atom, ikatan, dan koordinat XYZ asli yang sesuai."""
    from rdkit import Chem

    graph = Chem.Mol(pair.docked)
    Chem.Kekulize(graph, clearAromaticFlags=True)
    bond_types = {1: "singleBond", 2: "doubleBond", 3: "tripleBond"}
    lines = ["use strict;", "use utf8;", "use MdmDiscoveryScript;", "use SbdDiscoveryScript;",
             "my $document;", "my $value;", "my $view_error = '';", "eval {",
             "  $document = Mdm::Document::Create();"]
    for var, mol, rgb in (("native", pair.native, (42, 184, 213)),
                          ("docked", pair.docked, (255, 133, 82))):
        lines += [f"  my ${var} = $document->CreateMolecule();",
                  f"  ${var}->Name = {_perl_string(mol.GetProp('_Name'))};",
                  f"  my @{var}_atoms;", f"  my ${var}_color = Mdm::Color::Create();"]
        for channel, value in zip(("Red", "Green", "Blue"), rgb):
            lines.append(f"  ${var}_color->{channel} = {value};")
        for i, atom in enumerate(graph.GetAtoms()):
            x, y, z = mol.GetConformer().GetAtomPosition(i)
            lines += [f"  ${var}_atoms[{i}] = ${var}->CreateAtom({_perl_string(atom.GetSymbol())});",
                      f"  ${var}_atoms[{i}]->Name = '{atom.GetSymbol()}{i + 1}';",
                      f"  ${var}_atoms[{i}]->XYZ = Mdm::Point::Create({x:.12g}, {y:.12g}, {z:.12g});",
                      f"  ${var}_atoms[{i}]->Color = ${var}_color;"]
            if atom.GetFormalCharge():
                lines.append(f"  ${var}_atoms[{i}]->FormalCharge = Mdm::Rational::Create({atom.GetFormalCharge()}, 1);")
        for bond in graph.GetBonds():
            kind = bond_types.get(int(bond.GetBondTypeAsDouble()))
            if kind is None:
                raise ValueError("Jenis ikatan tidak didukung oleh pasangan BIOVIA.")
            lines.append(f"  $document->CreateBond(${var}_atoms[{bond.GetBeginAtomIdx()}], "
                         f"${var}_atoms[{bond.GetEndAtomIdx()}], Mdm::{kind});")
    lines += ["  $value = $document->CalculateHeavyAtomRmsd($native, $docked);",
              "  die 'BIOVIA tidak mengembalikan RMSD' unless defined $value;"]
    if overlay_path is not None:
        lines += ["  eval {", "    die 'SaveImage memerlukan client BIOVIA' if DiscoveryScript::IsStandalone();",
                  "    $document->SelectAll();",
                  "    $document->SetAtomDisplayStyle(Mdm::styleAtomStick);",
                  "    $document->DeselectAll();", "    $document->FitView();",
                  "    my $sebelum = $document->CreateScreenLabel('Sebelum redocking: native kristal', Mdm::Point2d::Create(-10.0, 8.5));",
                  "    $sebelum->Color = $native_color;",
                  "    my $sesudah = $document->CreateScreenLabel('Sesudah redocking: pose hasil docking', Mdm::Point2d::Create(-10.0, 7.6));",
                  "    $sesudah->Color = $docked_color;",
                  "    my $putih = Mdm::Color::Create(); $putih->Red = 245; $putih->Green = 245; $putih->Blue = 245;",
                  "    my $angka = $document->CreateScreenLabel(sprintf('RMSD %.3f Angstrom', $value), Mdm::Point2d::Create(-10.0, 6.7));",
                  "    $angka->Color = $putih;",
                  "    $document->UpdateViews();",
                  f"    $document->SaveImage({_perl_string(overlay_path.resolve().as_posix())}, 'png', 1200, 900);",
                  f"    die 'SaveImage tidak membuat PNG' unless -s {_perl_string(overlay_path.resolve().as_posix())};",
                  "  };", "  $view_error = $@ if $@;"]
    lines += ["};", "my $error = $@;", "$error =~ s/[\\r\\n\\t]+/ /g;",
              "$view_error =~ s/[\\r\\n\\t]+/ /g;",
              "eval { $document->Close() if $document; };",
              f"my $path = {_perl_string(result_path.resolve().as_posix())};",
              "open(my $out, '>', $path . '.tmp') or die $!;",
              f"print $out {_perl_string(token)} . \"\\t\" . (defined $value ? sprintf('%.12g', $value) : '') . \"\\t$error\\t$view_error\\n\";",
              "close($out) or die $!;", "rename($path . '.tmp', $path) or die $!;", ""]
    return "\n".join(lines)


@dataclass(frozen=True)
class BioviaRmsdMeasurement:
    rmsd: float
    transport: str
    report_path: Path
    overlay_path: Optional[Path] = None
    visualization_note: str = ""


def read_rmsd_result(path: Path, token: str, expected: float) -> Optional[tuple[float, str]]:
    """Tolak hasil lama, parsial, gagal, tidak finite, atau berbeda dari nilai pasangan."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.endswith("\n"):
        return None
    fields = text.rstrip("\r\n").split("\t")
    if len(fields) != 4 or fields[0] != token:
        return None
    if fields[2]:
        raise BioviaError(f"DiscoveryScript RMSD gagal: {fields[2]}")
    try:
        value = float(fields[1])
    except ValueError as exc:
        raise BioviaError("BIOVIA tidak mengembalikan angka RMSD.") from exc
    if not math.isfinite(value) or value < 0:
        raise BioviaError("BIOVIA mengembalikan RMSD tidak valid.")
    if not math.isclose(value, expected, abs_tol=0.002, rel_tol=0):
        raise BioviaError(f"RMSD BIOVIA {value:g} tidak cocok dengan pasangan pada posisi asli ({expected:g} A).")
    return value, fields[3]


class BioviaRmsdClient(BioviaClient):
    """Gunakan deteksi instalasi, pemeriksaan fokus, pembatalan, dan penjagaan tab yang ada."""

    def close_complex(self, stem: str) -> None:
        alias, folder = self._opened.get(stem, (stem, None))
        if folder is None and stem in self._opened:
            self._close_tabs(lambda name: name in (alias, alias + "*", alias + " *"))
            self._opened.pop(stem, None)
        else:
            super().close_complex(stem)

    def _menu(self, *items: str) -> None:
        for title in items:
            control = self._wait(lambda: self._menu_control(title),
                                 4, f"menu {title}")
            # Sebagian menu Qt menyediakan InvokePattern tanpa membuka menunya.
            # Gunakan input fisik dengan pemeriksaan fokus seperti pengekspor interaksi.
            self._click(control)
            time.sleep(0.15)

    def _menu_control(self, title: str):
        control = self._control(title=title, control_type="MenuItem")
        if control is not None:
            return control
        # Menu konteks Qt dapat berupa jendela popup terpisah dari jendela utama,
        # termasuk menu Run pada editor script.
        for hwnd, _, klass in self._top_windows():
            if hwnd == self._hwnd or not klass.startswith("Qt"):
                continue
            try:
                popup = self._rt.Application(backend="uia").connect(handle=hwnd).window(handle=hwnd)
                item = popup.child_window(title=title, control_type="MenuItem")
                if item.exists(timeout=0.1):
                    return item.wrapper_object()
            except Exception:
                continue
        return None

    def _paste_script(self, script: str) -> str:
        """Tempel ke Script Window baru milik ChemFlow dan pertahankan tab pengguna."""
        before = {t.window_text() for t in self._window.descendants(control_type="TabItem")}
        before_editors = {self._editor_id(e) for e in self._script_editors()}
        self._menu("File", "New", "Script Window")

        def new_tab():
            tabs = [t for t in self._window.descendants(control_type="TabItem")
                    if t.window_text() not in before and self._tab(lambda n: n == t.window_text()) is not None]
            return tabs[0] if len(tabs) == 1 else None

        tab = self._wait(new_tab, 10, "Script Window milik ChemFlow")
        alias = tab.window_text()
        self._opened[alias] = (alias, None)
        editors = [e for e in self._script_editors() if self._editor_id(e) not in before_editors]
        if len(editors) != 1:
            raise BioviaError("Editor Script Window tidak dikenali; memakai satu berkas script.")
        clipboard = self._rt.pyperclip
        previous = clipboard.paste()
        try:
            self._click(editors[0])
            clipboard.copy(script)
            self._keys("^a")
            self._keys("^v")
            time.sleep(0.2)
            # Baca ulang isi editor untuk memastikan penempelan berhasil.
            self._keys("^a")
            self._keys("^c")
            self._wait(lambda: clipboard.paste().replace("\r\n", "\n").rstrip("\n") == script.rstrip("\n"),
                       2, "isi script yang ditempel terverifikasi")
        finally:
            clipboard.copy(previous)
        self._run_script_editor(editors[0])
        return alias

    def _script_editors(self):
        return [c for c in self._window.descendants(control_type="Edit")
                if ("scintilla" in c.element_info.class_name.lower()
                    or c.element_info.class_name == "ScriptEditor::CodeEditor") and c.is_visible()]

    @staticmethod
    def _editor_id(editor):
        return tuple(editor.element_info.runtime_id)

    def _run_script_editor(self, editor) -> None:
        bars = self._window.descendants(control_type="ToolBar")
        run = [c for bar in bars if "script" in bar.window_text().lower()
               for c in bar.descendants() if c.window_text() == "Run" and c.is_enabled()]
        if not run:
            self._lock.pulse()
            self._ensure_foreground()
            editor.click_input(button="right")
            item = self._wait(lambda: self._menu_control("Run"),
                              3, "menu konteks Run script")
            self._click(item)
        else:
            self._click(run[0])

    def _execute_script_file(self, path: Path) -> str:
        # Gunakan client yang sudah tersambung. Sebagian versi DS mengabaikan
        # argumen script yang diteruskan oleh proses executable kedua.
        alias = f"cf_rmsd_{uuid.uuid4().hex[:12]}"
        folder = Path(tempfile.mkdtemp(prefix="chemflow_biovia_rmsd_"))
        script = folder / f"{alias}.pl"
        shutil.copyfile(path, script)
        self._opened[alias] = (alias, folder)
        before_editors = {self._editor_id(e) for e in self._script_editors()}
        self._focus()
        self._keys("{ESC}")
        self._keys("^o")
        dialog = self._wait(lambda: next((w for w in self._dialogs()
                                          if w[1] == "Open" and w[2] == "#32770"), None),
                            10, "dialog Open script RMSD")
        box = self._rt.Application(backend="uia").connect(handle=dialog[0]).window(handle=dialog[0])
        box.child_window(title="File name:", control_type="ComboBox").child_window(
            control_type="Edit").set_edit_text(str(script))
        self._keys("{ENTER}")
        self._wait(lambda: not any(w[2] == "#32770" for w in self._dialogs()),
                   20, "dialog Open script menutup")
        # Bawaan DS menjalankan berkas .pl saat dibuka. Bila pengguna memilih
        # editor sebagai bawaan, jalankan hanya tab script milik ChemFlow.
        tab = self._tab(lambda name: name == alias)
        if tab is not None:
            self._click(tab)
            editors = [e for e in self._script_editors() if self._editor_id(e) not in before_editors]
            if len(editors) != 1:
                raise BioviaError("Editor script berkas ChemFlow tidak dapat diidentifikasi dengan aman.")
            self._run_script_editor(editors[0])
        return alias

    def calculate_rmsd(self, pair: RmsdPair, directory: Path, *,
                       save_overlay: bool = True, timeout: float = 30.0) -> BioviaRmsdMeasurement:
        directory.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        report = directory / "biovia_result.tsv"
        # Nama gambar unik per eksekusi mencegah PNG lama dianggap sebagai hasil baru.
        overlay = directory / f"biovia_overlay_{token}.png" if save_overlay else None
        script = build_rmsd_script(pair, token, report, overlay)
        path = directory / "biovia_rmsd.pl"
        path.write_text(script, encoding="utf-8")
        alias, transport = None, "clipboard"
        try:
            if getattr(self, "_clipboard_available", None) is False:
                alias = self._execute_script_file(path)
                transport = "script_file"
            else:
                try:
                    alias = self._paste_script(script)
                    self._clipboard_available = True
                except Exception as exc:
                    self._clipboard_available = False
                    self._log.info(f"Clipboard RMSD BIOVIA tidak tersedia ({exc}); menjalankan satu script.")
                    self.recover()
                    alias = self._execute_script_file(path)
                    transport = "script_file"
            value, note = self._wait(lambda: read_rmsd_result(report, token, pair.rmsd),
                                     timeout, "hasil CalculateHeavyAtomRmsd BIOVIA")
            image = None
            if overlay is not None:
                try:
                    from PIL import Image

                    with Image.open(overlay) as picture:
                        picture.verify()
                    image = overlay
                except Exception as exc:
                    note = (note + f" Visualisasi BIOVIA tidak terbentuk: {exc}").strip()
            return BioviaRmsdMeasurement(value, transport, report, image, note)
        finally:
            if alias is not None:
                self.close_complex(alias)
