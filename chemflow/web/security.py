"""Autentikasi satu operator, sesi berbatas, dan validasi CSRF."""
from __future__ import annotations
import hashlib
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from fastapi import HTTPException, Request
COOKIE = "chemflow_session"

@dataclass
class Auth:
    password: str
    sessions: dict = field(default_factory=dict)
    attempts: deque = field(default_factory=deque)
    ttl: int = 8 * 3600

    def login(self, password: str) -> tuple[str, str]:
        now = time.time()
        while self.attempts and self.attempts[0] < now - 60:
            self.attempts.popleft()
        if len(self.attempts) >= 10:
            raise HTTPException(429, "Terlalu banyak percobaan. Tunggu satu menit.")
        if not secrets.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(self.password.encode()).digest()):
            self.attempts.append(now)
            raise HTTPException(401, "Kata sandi tidak cocok.")
        self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}
        if len(self.sessions) >= 64:
            self.sessions.pop(next(iter(self.sessions)))
        session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.sessions[session] = (csrf, now + self.ttl)
        return session, csrf

    def require(self, request: Request) -> str:
        session = request.cookies.get(COOKIE, "")
        value = self.sessions.get(session)
        if not value or value[1] <= time.time():
            self.sessions.pop(session, None)
            raise HTTPException(401, "Sesi berakhir. Silakan masuk kembali.")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), value[0]):
                raise HTTPException(403, "Token keamanan tidak valid. Muat ulang halaman.")
        return value[0]


def check_origin(request: Request) -> None:
    from urllib.parse import urlsplit
    origin = request.headers.get("origin")
    if origin and (urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme != request.url.scheme):
        raise HTTPException(403, "Permintaan harus berasal dari situs ChemFlow ini.")
