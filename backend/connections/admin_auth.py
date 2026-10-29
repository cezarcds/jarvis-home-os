"""Senha local do admin (bcrypt), sessões em memória e proteções de rota."""
import base64
import hashlib
import secrets
import threading
import time
from typing import Optional

import bcrypt
from fastapi import Header, HTTPException, Request

from . import db
from .config import allowed_origins

PASSWORD_KEY = "admin.password_hash"
MIN_PASSWORD = 8
SESSION_TTL = 30 * 60          # sessão expira após 30 min sem uso
MAX_FAILURES = 5
LOCK_SECONDS = 60

_lock = threading.Lock()
_sessions: dict[str, float] = {}
_failures = {"count": 0, "locked_until": 0.0}


def _prehash(password: str) -> bytes:
    # bcrypt só lê 72 bytes; o pré-hash evita truncar senhas longas em silêncio.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def is_password_set() -> bool:
    return db.get_setting(PASSWORD_KEY) is not None


def set_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.")
    hashed = bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")
    db.set_setting(PASSWORD_KEY, hashed)
    db.audit("admin.password_set")


class Locked(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds


def verify_password(password: str) -> bool:
    now = time.time()
    with _lock:
        if _failures["locked_until"] > now:
            raise Locked(int(_failures["locked_until"] - now) + 1)
    stored = db.get_setting(PASSWORD_KEY)
    ok = bool(stored) and bcrypt.checkpw(_prehash(password), stored.encode("ascii"))
    with _lock:
        if ok:
            _failures.update(count=0, locked_until=0.0)
        else:
            _failures["count"] += 1
            if _failures["count"] >= MAX_FAILURES:
                _failures.update(count=0, locked_until=time.time() + LOCK_SECONDS)
    if not ok:
        db.audit("admin.login_failed")
    return ok


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = time.time() + SESSION_TTL
    return token


def validate_session(token: Optional[str]) -> bool:
    if not token:
        return False
    now = time.time()
    with _lock:
        for t in [t for t, exp in _sessions.items() if exp < now]:
            del _sessions[t]
        if token in _sessions:
            _sessions[token] = now + SESSION_TTL  # renova a cada uso
            return True
    return False


def end_session(token: Optional[str]) -> None:
    with _lock:
        _sessions.pop(token or "", None)


def reset_state() -> None:
    """Só para testes."""
    with _lock:
        _sessions.clear()
        _failures.update(count=0, locked_until=0.0)


# ---- dependências do FastAPI ------------------------------------------------

def check_origin(request: Request) -> None:
    """Bloqueia chamadas vindas de outros sites abertos no seu navegador (CSRF).
    Navegadores sempre enviam Origin em POST/PUT cross-site; curl e testes não enviam."""
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in allowed_origins():
        raise HTTPException(status_code=403, detail="Origem não autorizada.")


def require_admin(request: Request, x_jarvis_admin: Optional[str] = Header(default=None)) -> str:
    check_origin(request)
    if not validate_session(x_jarvis_admin):
        raise HTTPException(status_code=401, detail="Sessão de administrador ausente ou expirada.")
    return x_jarvis_admin  # type: ignore[return-value]
