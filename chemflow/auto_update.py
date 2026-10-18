"""Runtime rilis GitHub otomatis bertahap yang dipakai bersama CLI dan WebUI.

Tidak pernah menimpa checkout atau lingkungan aktif. Lingkungan terisolasi yang
baru diaktifkan secara atomik hanya setelah versi, impor, dan aset WebUI lolos.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import requests
from chemflow import __version__

REPOSITORY = "Arifmaulanaazis/chemflow"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def version(value):
    match = TAG.fullmatch(str(value))
    if not match:
        raise ValueError("Versi release harus semver stabil.")
    return tuple(map(int, match.groups()))


def dirty_checkout():
    root = Path(__file__).resolve().parents[1]
    if not (root / ".git").exists():
        return False
    try:
        return bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], timeout=5, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.SubprocessError):
        return True


class AutoUpdater:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("CHEMFLOW_UPDATE_HOME") or Path.home()/".cache"/"chemflow"/"updates").resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def read(self, name):
        try:
            return json.loads((self.root/name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def write(self, name, value):
        temporary = self.root / (name+f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(self.root/name)

    def state(self):
        return {"mode": "automatic" if os.environ.get("CHEMFLOW_AUTO_UPDATE", "1") != "0" else "disabled", **self.read("state.json")}

    def active(self):
        value = self.read("active.json")
        try:
            release = value["version"]
            if version(release) <= version(__version__):
                return None
            directory=value.get("directory",release)
            if not re.fullmatch(r"[0-9.]+(?:-[a-f0-9]{32})?",directory):return None
            folder = (self.root/"versions"/directory).resolve()
            executable = folder/("Scripts/python.exe" if os.name=="nt" else "bin/python")
            if not folder.is_relative_to(self.root/"versions") or not executable.is_relative_to(folder) or not executable.is_file() or not (folder/"pyvenv.cfg").is_file():
                return None
            return executable
        except (KeyError, ValueError, OSError):
            return None

    def check(self, force=False):
        cached = self.read("release.json")
        if not force and time.time()-cached.get("checked",0) < 6*3600:
            release = cached.get("release",{})
        else:
            response=requests.get(API, headers={"Accept":"application/vnd.github+json"},timeout=8)
            response.raise_for_status();release=response.json()
            version(release["tag_name"])
            self.write("release.json",{"checked":time.time(),"release":release})
        return release

    @contextmanager
    def install_lock(self):
        handle=(self.root/"install.lock").open("a+b");handle.write(b"0");handle.flush();handle.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield
        finally:
            handle.close()

    def command(self, args, cwd=None, timeout=900):
        env=dict(os.environ,CHEMFLOW_SKIP_UPDATE="1",PIP_DISABLE_PIP_VERSION_CHECK="1")
        with (self.root/"install.log").open("ab") as log:
            subprocess.run(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout,shell=False,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))

    def download(self,url,target,digest=None):
        pattern=r"https://github\.com/Arifmaulanaazis/chemflow/(?:releases/download/v?[0-9]+\.[0-9]+\.[0-9]+/chemflow-[0-9.]+-py3-none-any\.whl|archive/refs/tags/v?[0-9]+\.[0-9]+\.[0-9]+\.zip)"
        if not re.fullmatch(pattern,url):
            raise ValueError("Sumber pembaruan bukan release resmi ChemFlow.")
        size=0;checksum=hashlib.sha256()
        with requests.get(url,timeout=(10,60),stream=True) as response:
            response.raise_for_status()
            with target.open("wb") as stream:
                for chunk in response.iter_content(1024*1024):
                    size+=len(chunk)
                    if size>150*1024**2:raise ValueError("Paket update melebihi 150 MB.")
                    checksum.update(chunk);stream.write(chunk)
        if digest and digest != "sha256:"+checksum.hexdigest():
            raise ValueError("Checksum paket update tidak cocok.")

    def stage(self, release):
        tag=release["tag_name"];number=".".join(map(str,version(tag)))
        folder=self.root/"versions"/(number+"-"+uuid.uuid4().hex)
        folder.parent.mkdir(parents=True,exist_ok=True)
        if not folder.parent.resolve().is_relative_to(self.root):raise ValueError("Folder runtime keluar dari cache update.")
        try:
            self.command([sys.executable,"-m","venv",str(folder)])
            executable=folder/("Scripts/python.exe" if os.name=="nt" else "bin/python")
            with tempfile.TemporaryDirectory(prefix="chemflow-release-",dir=self.root) as temporary:
                work=Path(temporary)
                asset=next((a for a in release.get("assets",[]) if re.fullmatch(r"chemflow-[0-9.]+-py3-none-any\.whl",a.get("name",""))),None)
                if asset:
                    package=work/asset["name"]
                    self.download(asset["browser_download_url"],package,asset.get("digest"))
                    install=str(package)+"[web]"
                else:
                    archive=work/"release.zip"
                    self.download(f"https://github.com/{REPOSITORY}/archive/refs/tags/{tag}.zip",archive)
                    with zipfile.ZipFile(archive) as zipped:
                        if sum(i.file_size for i in zipped.infolist())>300*1024**2 or len(zipped.infolist())>20000:
                            raise ValueError("Arsip release terlalu besar.")
                        for item in zipped.infolist():
                            # ZipInfo menormalkan backslash di Windows; validasi
                            # nama asli arsip sebelum ekstraksi apa pun.
                            original=item.orig_filename
                            path=PurePosixPath(original)
                            if path.is_absolute() or ".." in path.parts or ":" in original or "\\" in original or stat.S_ISLNK(item.external_attr>>16):
                                raise ValueError("Path arsip tidak aman.")
                        zipped.extractall(work/"source")
                    roots=list((work/"source").iterdir())
                    if len(roots)!=1 or not (roots[0]/"pyproject.toml").exists():raise ValueError("Struktur source release tidak valid.")
                    source=roots[0]
                    if (source/"frontend/package-lock.json").exists():
                        npm=shutil.which("npm.cmd" if os.name=="nt" else "npm")
                        if not npm:raise RuntimeError("Release source memerlukan Node/npm untuk build WebUI; wheel resmi tidak memerlukan npm.")
                        # npm.cmd hanyalah peluncur Windows; jalankan CLI JS npm lewat Node
                        # agar shell=False dan vektor argumen tetap berbatas.
                        if os.name=="nt":
                            npm_cli=Path(npm).parent/"node_modules/npm/bin/npm-cli.js"
                            command=[shutil.which("node") or "node",str(npm_cli)]
                        else:command=[npm]
                        self.command([*command,"ci"],cwd=source/"frontend")
                        self.command([*command,"run","build"],cwd=source/"frontend")
                    install=str(source)+"[web]"
                self.command([str(executable),"-m","pip","install","--no-input",install])
            probe="import chemflow,chemflow.cli;from pathlib import Path;import chemflow.web.server as w;assert chemflow.__version__=="+repr(number)+";assert (Path(w.__file__).parent/'static/index.html').is_file()"
            self.command([str(executable),"-I","-c",probe],timeout=60)
            self.write("active.json",{"version":number,"directory":folder.name,"activated":time.time()})
            return executable
        except BaseException:
            if folder.resolve().is_relative_to((self.root/"versions").resolve()) and self.read("active.json").get("directory")!=folder.name:
                shutil.rmtree(folder,ignore_errors=True)
            raise

    def maybe_update(self, force=False):
        if os.environ.get("CHEMFLOW_AUTO_UPDATE","1")=="0" or os.environ.get("CHEMFLOW_SKIP_UPDATE")=="1":return None
        if dirty_checkout():
            self.write("state.json",{"status":"deferred","message":"Source lokal memiliki perubahan; update otomatis ditunda agar perubahan Anda tetap aman."})
            return None
        active=self.active()
        if active:return active
        previous=self.read("state.json")
        if not force and previous.get("status")=="failed" and time.time()-previous.get("attempt",0)<6*3600:return None
        try:
            release=self.check(force)
            if version(release["tag_name"])<=version(__version__):
                self.write("state.json",{"status":"current","message":"Versi stabil terbaru sudah digunakan."});return None
            with self.install_lock():
                active=self.active()
                if active:return active
                self.write("state.json",{"status":"installing","latest":release["tag_name"],"attempt":time.time(),"message":"Menyiapkan dan memverifikasi runtime baru."})
                executable=self.stage(release)
                self.write("state.json",{"status":"ready","latest":release["tag_name"],"message":"Pembaruan terverifikasi; runtime baru siap digunakan."})
                return executable
        except Exception as exc:
            self.write("state.json",{"status":"failed","attempt":time.time(),"message":str(exc)[:500]})
            return None


def launch(executable,argv):
    os.environ["CHEMFLOW_SKIP_UPDATE_ONCE"]="1"
    os.execv(str(executable),[str(executable),"-I","-m","chemflow",*argv])


def cli_bootstrap(argv):
    if os.environ.pop("CHEMFLOW_SKIP_UPDATE_ONCE",None) or os.environ.get("CHEMFLOW_SKIP_UPDATE")=="1":return
    try:
        updater=AutoUpdater();executable=updater.maybe_update()
        if executable:
            print("[ChemFlow] Pembaruan siap. Memulai versi terbaru…",flush=True,file=sys.stderr);launch(executable,argv)
        elif updater.state().get("status") in {"deferred","failed"}:
            print("[ChemFlow update] "+updater.state().get("message",""),flush=True,file=sys.stderr)
    except (OSError,ValueError):
        pass  # A read-only home must not prevent scientific work.
