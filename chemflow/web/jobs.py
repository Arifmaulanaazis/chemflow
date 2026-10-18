"""Antrean job serial yang persisten, proses anak CLI terisolasi, pembatalan, dan pemulihan."""
from __future__ import annotations
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
import psutil
from fastapi import HTTPException
from .schema import build_arguments
from .storage import confined


class JobManager:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        for name in ("runs", "uploads", "logs", "prompts"):
            (workspace / name).mkdir(parents=True, exist_ok=True)
        self.db = workspace / "jobs.sqlite3"
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.process = None
        self.maintenance = False
        self.active_id = None
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, name TEXT, command TEXT, status TEXT, created REAL, started REAL, finished REAL, exit_code INTEGER, output TEXT, argv TEXT)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connection() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 500")]
        for r in rows:
            r.pop("argv")
            output = r.pop("output")
            try:
                progress = json.loads((confined(self.workspace / "runs", output) / "_state/progress.json").read_text())
                r["stage"] = progress.get("stage")
            except (OSError, ValueError):
                r["stage"] = None
            r["pending_input"] = bool(self.pending_inputs(r["id"], status=r["status"]))
        return rows

    def get(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Run tidak ditemukan.")
        return dict(row)

    def output(self, job_id):
        return confined(self.workspace / "runs", self.get(job_id)["output"])

    def resolve_input(self, value):
        if value.startswith("run:"):
            try:
                _, job_id, relative = value.split(":", 2)
            except ValueError:
                raise HTTPException(422, "Referensi input run tidak valid.")
            path = confined(self.output(job_id), relative)
        else:
            path = confined(self.workspace / "uploads", value)
        if not path.exists() or path.is_symlink():
            raise HTTPException(422, "Berkas input tidak ditemukan. Unggah ulang.")
        return path

    def create(self, command, options, name, source_run=None):
        job_id = uuid.uuid4().hex
        output_id = self.get(source_run)["output"] if source_run else job_id
        if command in {"resume", "similarity", "interactions"} and not source_run:
            raise HTTPException(422, "Pilih run sumber.")
        output = confined(self.workspace / "runs", output_id)
        if command == "gcms" and not source_run and not options.get("data"):
            raise HTTPException(422, "Unggah data GC-MS atau pilih run sumber.")
        argv = build_arguments(command, options, output, self.resolve_input)
        with self.lock, self.connection() as db:
            if self.maintenance:
                raise HTTPException(503,"Pembaruan server sedang disiapkan. Coba kembali setelah server tersambung.")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 32:
                raise HTTPException(429, "Antrean penuh (32 job). Tunggu hingga job selesai.")
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)", (job_id, name.strip() or command, command, "queued", time.time(), None, None, None, output_id, json.dumps(argv)))
        return job_id

    def import_run(self, source):
        source = Path(source).resolve()
        if not source.is_dir() or source == self.workspace or self.workspace.is_relative_to(source):
            raise ValueError("Folder impor tidak valid atau memuat workspace tujuan.")
        job_id = uuid.uuid4().hex
        target = self.workspace / "runs" / job_id
        if target.is_relative_to(source):
            raise ValueError("Folder impor tidak boleh memuat folder tujuan.")
        target.mkdir()
        for directory, dirs, files in os.walk(source, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
            for name in files:
                file = Path(directory) / name
                if file.is_symlink() or not file.resolve().is_relative_to(source):
                    continue
                dest = target / file.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
        with self.connection() as db:
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)", (job_id, f"Impor {source.name}", "run", "imported", time.time(), None, time.time(), None, job_id, "[]"))
        return job_id

    def begin_maintenance(self):
        with self.lock, self.connection() as db:
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:
                return False
            self.maintenance = True
            return True

    def start(self):
        self.lease = (self.workspace / ".server.lock").open("a+b")
        self.lease.write(b"0")
        self.lease.flush()
        self.lease.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lease.close()
            raise RuntimeError("Workspace sudah dipakai server lain. Gunakan workspace berbeda.")
        with self.connection() as db:
            db.execute("UPDATE jobs SET status='interrupted',finished=? WHERE status='running'", (time.time(),))
        self.thread = threading.Thread(target=self._work, daemon=True, name="chemflow-jobs")
        self.thread.start()

    def _work(self):
        while not self.stop_event.wait(.25):
            with self.lock, self.connection() as db:
                row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
                if row is None:
                    continue
                job = dict(row)
                db.execute("UPDATE jobs SET status='running',started=? WHERE id=?", (time.time(), job["id"]))
                self.active_id = job["id"]
            try:
                output = self.output(job["id"])
                output.mkdir(parents=True, exist_ok=True)
                env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1", MPLBACKEND="Agg")
                # Kredensial login operator tidak pernah diteruskan ke proses anak ilmiah.
                env.pop("CHEMFLOW_WEB_PASSWORD", None)
                env["CHEMFLOW_SKIP_UPDATE"] = "1"
                env["CHEMFLOW_PROMPT_DIR"] = str(self.workspace / "prompts" / job["id"])
                with (self.workspace / "logs" / f"{job['id']}.log").open("wb") as log:
                    with self.lock:
                        if self.get(job["id"])["status"] != "running":
                            continue
                        self.process = subprocess.Popen([sys.executable, "-m", "chemflow", *json.loads(job["argv"])], stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, shell=False, env=env,
                            cwd=str(Path(__file__).resolve().parents[2]),
                            start_new_session=os.name != "nt", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
                    code = self.process.wait()
                with self.lock, self.connection() as db:
                    db.execute("UPDATE jobs SET status=?,finished=?,exit_code=? WHERE id=? AND status='running'",
                               ("succeeded" if code == 0 else "failed", time.time(), code, job["id"]))
            except Exception as exc:
                (self.workspace / "logs" / f"{job['id']}.log").write_text(str(exc), encoding="utf-8")
                with self.connection() as db:
                    db.execute("UPDATE jobs SET status='failed',finished=? WHERE id=? AND status='running'", (time.time(), job["id"]))
            finally:
                with self.lock:
                    self.process = None
                    self.active_id = None

    def cancel(self, job_id, status="cancelled"):
        with self.lock:
            job = self.get(job_id)
            if job["status"] not in {"queued", "running"}:
                raise HTTPException(409, "Run sudah berhenti.")
            with self.connection() as db:
                db.execute("UPDATE jobs SET status=?,finished=? WHERE id=?", (status, time.time(), job_id))
            if self.active_id == job_id and self.process and self.process.poll() is None:
                try:
                    parent = psutil.Process(self.process.pid)
                    children = parent.children(recursive=True)
                    for proc in [*children, parent]:
                        try:
                            proc.terminate()
                        except psutil.NoSuchProcess:
                            pass
                    _, alive = psutil.wait_procs([*children, parent], timeout=3)
                    for proc in alive:
                        try:
                            proc.kill()
                        except psutil.NoSuchProcess:
                            pass
                except psutil.NoSuchProcess:
                    pass

    def pending_inputs(self, job_id, status=None):
        if status is None:
            status = self.get(job_id)["status"]
        if status != "running":
            return []
        folder = self.workspace / "prompts" / job_id
        result = []
        for path in sorted(folder.glob("*.request.json")):
            token = path.name.split(".")[0]
            if not (folder / f"{token}.response.json").exists():
                try:
                    result.append(json.loads(path.read_text(encoding="utf-8")))
                except FileNotFoundError:
                    pass  # Child consumed a reply between glob and read.
        return result

    def answer_input(self, job_id, prompt_id, answer):
        from .prompts import validate_answer
        with self.lock:
            pending = next((p for p in self.pending_inputs(job_id) if p["id"] == prompt_id), None)
            if pending is None:
                raise HTTPException(409, "Permintaan sudah dijawab atau job tidak aktif.")
            result = validate_answer(pending, answer)
            folder = self.workspace / "prompts" / job_id
            temporary = folder / f"{prompt_id}.tmp"
            temporary.write_text(json.dumps(result), encoding="utf-8")
            temporary.replace(folder / f"{prompt_id}.response.json")

    def logs(self, job_id):
        self.get(job_id)
        path = self.workspace / "logs" / f"{job_id}.log"
        if not path.exists():
            return ""
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            return stream.read(65536).decode("utf-8", errors="replace")

    def close(self):
        self.stop_event.set()
        if self.active_id:
            try:
                self.cancel(self.active_id, "interrupted")
            except HTTPException:
                pass
        if hasattr(self, "thread"):
            self.thread.join(timeout=6)
        if hasattr(self, "lease") and not self.lease.closed:
            self.lease.close()
