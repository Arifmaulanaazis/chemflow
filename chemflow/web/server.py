"""API same-origin dan SPA statis. Jalankan satu worker server per workspace."""
from __future__ import annotations
import asyncio
import json
import mimetypes
import os
import platform
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
import psutil
from chemflow import __version__
from .jobs import JobManager
from .schema import schema
from .security import Auth, COOKIE, check_origin
from .storage import MAX_UPLOAD, UPLOAD_EXTENSIONS, artifacts, confined, preview
from .updates import UpdateChecker


class Login(BaseModel):
    password: str = Field(max_length=1024)


class JobRequest(BaseModel):
    command: str
    name: str = Field(default="", max_length=120)
    options: dict = Field(default_factory=dict)
    source_run: str | None = None


def create_app(workspace: Path, password: str, allowed_hosts=None, secure_cookie=False, run_worker=True, check_updates=True, import_runs=()):
    if len(password) < 12:
        raise ValueError("CHEMFLOW_WEB_PASSWORD minimal 12 karakter.")
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    auth = Auth(password)
    manager = JobManager(workspace)
    updates = UpdateChecker()

    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            manager.start()
            try:
                for source in import_runs:
                    manager.import_run(source)
            except Exception:
                manager.close()
                raise
        task = None
        if check_updates:
            async def watch_updates():
                while True:
                    result=await asyncio.to_thread(updates.check)
                    if result.get("status")=="available" and app.state.request_update_restart and manager.begin_maintenance():
                        from chemflow.auto_update import AutoUpdater
                        try:
                            executable=await asyncio.to_thread(AutoUpdater().maybe_update)
                            if executable:
                                app.state.update_runtime=executable
                                app.state.request_update_restart()
                                return
                        finally:
                            if not app.state.update_runtime:
                                manager.maintenance=False
                    await asyncio.sleep(60)
            task = asyncio.create_task(watch_updates())
        yield
        if task:
            task.cancel()
        await asyncio.to_thread(manager.close)

    app = FastAPI(title="ChemFlow Web API", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.state.auth = auth
    app.state.updates = updates
    app.state.update_runtime = None
    app.state.request_update_restart = None
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["localhost", "127.0.0.1", "[::1]"])

    @app.middleware("http")
    async def guards(request, call_next):
        try:
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                check_origin(request)
            if request.url.path.startswith("/api/") and request.url.path != "/api/login":
                auth.require(request)
            response = await call_next(request)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response.headers["X-ChemFlow-Version"] = __version__
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/login")
    def login(body: Login):
        session, csrf = auth.login(body.password)
        response = JSONResponse({"csrf": csrf})
        response.set_cookie(COOKIE, session, httponly=True, secure=secure_cookie, samesite="strict", max_age=auth.ttl)
        return response

    @app.get("/api/session")
    def session(request: Request):
        return {"csrf": auth.require(request), "version": __version__}

    @app.post("/api/logout")
    def logout(request: Request):
        auth.sessions.pop(request.cookies.get(COOKIE), None)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        return response

    @app.get("/api/openapi.json")
    def openapi():
        return app.openapi()

    @app.get("/api/schema")
    def get_schema():
        return {"commands": schema(), "platform": platform.system(), "version": __version__,
                "biovia": platform.system() == "Windows", "max_upload_mb": MAX_UPLOAD // 1024**2}

    @app.get("/api/jobs")
    def jobs():
        return manager.list()

    @app.post("/api/jobs", status_code=201)
    def create_job(body: JobRequest):
        if body.command == "interactions" and platform.system() != "Windows":
            raise HTTPException(422, "Ekspor BIOVIA memerlukan desktop Windows aktif. Preview hasil tersedia di semua OS.")
        return {"id": manager.create(body.command, body.options, body.name, body.source_run)}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        manager.cancel(job_id)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/inputs")
    def pending_inputs(job_id: str):
        return manager.pending_inputs(job_id)

    @app.post("/api/jobs/{job_id}/inputs/{prompt_id}")
    def answer_input(job_id: str, prompt_id: str, answer: dict):
        manager.answer_input(job_id, prompt_id, answer)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/logs")
    def logs(job_id: str):
        return {"text": manager.logs(job_id)}

    @app.get("/api/jobs/{job_id}/artifacts")
    def get_artifacts(job_id: str):
        return artifacts(manager.output(job_id))

    def artifact(job_id, path):
        target = confined(manager.output(job_id), path)
        if not target.is_file():
            raise HTTPException(404, "Berkas belum tersedia.")
        return target

    @app.get("/api/jobs/{job_id}/preview")
    def get_preview(job_id: str, path: str, sheet: str | None = None):
        return preview(artifact(job_id, path), sheet)

    @app.get("/api/jobs/{job_id}/file")
    def file(job_id: str, path: str, download: bool = True):
        target = artifact(job_id, path)
        inline = not download and target.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".pdb", ".pdbqt", ".sdf", ".mol", ".mol2"}
        return FileResponse(target, filename=target.name, media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream",
                            content_disposition_type="inline" if inline else "attachment")

    @app.get("/api/uploads")
    def uploads():
        return [{"id": p.parent.name + "/" + p.name, "name": p.name, "size": p.stat().st_size} for p in (workspace / "uploads").glob("*/*") if p.is_file() and p.resolve().is_relative_to(workspace / "uploads")]

    @app.post("/api/uploads", status_code=201)
    async def upload(request: Request, filename: str):
        filename = filename.replace("\\", "/").split("/")[-1]
        if not re.fullmatch(r"[\w .()\-]{1,150}", filename) or Path(filename).suffix.lower() not in UPLOAD_EXTENSIONS:
            raise HTTPException(422, "Nama/format berkas tidak didukung.")
        upload_id = uuid.uuid4().hex
        folder = workspace / "uploads" / upload_id
        folder.mkdir()
        target = folder / filename
        size = 0
        try:
            with target.open("wb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, "Maksimum unggahan 100 MB per berkas.")
                    stream.write(chunk)
            if size == 0:
                raise HTTPException(422, "Berkas kosong.")
        except BaseException:
            target.unlink(missing_ok=True)
            folder.rmdir()
            raise
        return {"id": upload_id + "/" + filename, "name": filename, "size": size}

    @app.get("/api/resources")
    def resources():
        mem, disk = psutil.virtual_memory(), psutil.disk_usage(str(workspace))
        return {"cpu": psutil.cpu_percent(), "cores": psutil.cpu_count(), "ram_percent": mem.percent, "ram_used": mem.used, "ram_total": mem.total,
                "disk_percent": disk.percent, "disk_free": disk.free, "platform": platform.system(), "time": time.time()}

    vina_cache = {"time": 0, "items": []}

    @app.get("/api/vina-versions")
    def vina_versions():
        from chemflow.docking.vina_manager import VinaReleaseManager
        if time.time() - vina_cache["time"] > 3600:
            try:
                assets = VinaReleaseManager().list_compatible()
            except RuntimeError as exc:
                raise HTTPException(502, str(exc)) from exc
            vina_cache.update(time=time.time(), items=[{"version": a.version, "label": a.label} for a in assets])
        return vina_cache["items"]

    @app.get("/api/updates")
    async def get_updates():
        result=await asyncio.to_thread(updates.check)
        from chemflow.auto_update import AutoUpdater
        try: result["automatic"]=AutoUpdater().state()
        except OSError: result["automatic"]={"mode":"automatic","status":"unavailable"}
        return result

    @app.get("/api/events")
    async def events(request: Request):
        async def stream():
            while not await request.is_disconnected():
                if app.state.update_runtime:
                    yield 'event: updating\ndata: {}\n\n'
                    break
                try:
                    auth.require(request)
                except HTTPException:
                    yield 'event: expired\ndata: {}\n\n'
                    break
                snapshot = await asyncio.to_thread(lambda: {"jobs": manager.list(), "resources": resources()})
                yield "data: " + json.dumps(snapshot) + "\n\n"
                await asyncio.sleep(2)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache, no-transform"})

    from .receptors import router
    app.include_router(router(workspace))
    from .ligands import router as ligand_router
    app.include_router(ligand_router(workspace))
    from .library import router as library_router
    app.include_router(library_router())

    static = Path(__file__).parent / "static"

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Endpoint tidak ditemukan.")
        if path:
            candidate = confined(static, path)
            if candidate.is_file():
                return FileResponse(candidate)
        if (static / "index.html").exists():
            return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "WebUI belum dibangun. Jalankan npm ci dan npm run build di frontend/."}, status_code=503)

    return app


def serve(args):
    try:
        import uvicorn
    except ImportError:
        print('Pasang WebUI: pip install -e ".[web]"')
        return 1
    password = os.environ.get("CHEMFLOW_WEB_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(24)
        print(f"Kata sandi sesi WebUI: {password}")
    if len(password) < 12:
        print("CHEMFLOW_WEB_PASSWORD minimal 12 karakter.")
        return 1
    hosts = list(dict.fromkeys(["localhost", "127.0.0.1", "[::1]", *args.allowed_host]))
    if args.host not in {"0.0.0.0", "::"}:
        hosts.append(args.host)
    if any("*" in host or "/" in host or ":" in host and host != "[::1]" for host in hosts):
        print("--allowed-host harus hostname/IP eksplisit tanpa port atau wildcard.")
        return 1
    app = create_app(args.workspace, password, hosts, args.secure_cookie, import_runs=args.import_run)
    print(f"ChemFlow WebUI: http://{args.host}:{args.port} (Ctrl+C untuk berhenti)")
    import ipaddress
    proxies = ["127.0.0.1", "::1"]
    try:
        proxies += [str(ipaddress.ip_address(value)) for value in args.trusted_proxy]
    except ValueError:
        print("--trusted-proxy harus alamat IP eksplisit tanpa wildcard/subnet.")
        return 1
    config=uvicorn.Config(app, host=args.host, port=args.port, forwarded_allow_ips=",".join(proxies), workers=1, timeout_graceful_shutdown=10)
    server=uvicorn.Server(config)
    app.state.request_update_restart=lambda: setattr(server,"should_exit",True)
    server.run()
    if app.state.update_runtime:
        from chemflow.auto_update import launch
        os.environ["CHEMFLOW_WEB_PASSWORD"]=password
        # Pertahankan path workspace absolut lintas runtime terkelola yang terisolasi.
        import sys
        original=["web","--host",args.host,"--port",str(args.port),"--workspace",str(Path(args.workspace).resolve())]
        for host in args.allowed_host:original.extend(["--allowed-host",host])
        for proxy in args.trusted_proxy:original.extend(["--trusted-proxy",proxy])
        if args.secure_cookie:original.append("--secure-cookie")
        launch(app.state.update_runtime,original)
    return 0
