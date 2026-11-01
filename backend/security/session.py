"""Token de sessão do HUD e guarda das rotas locais.

Por que existe: o backend só escuta 127.0.0.1, mas qualquer site aberto no navegador consegue
mandar requisições para ele (CSRF) e, com DNS rebinding, até ler as respostas. Três barreiras:

1. Host: só aceita localhost/127.0.0.1 na porta do backend (derrota DNS rebinding).
2. Origin: se o navegador mandou Origin, ele precisa estar na allowlist.
3. Token: header X-Jarvis-Token, comparado em tempo constante.

O token fica num arquivo em ~/.jarvis (fora do repositório; `data_dir()` recusa pasta dentro de
um repo). Ele sobrevive a reinício do backend: um HUD já aberto, ou outro cliente local como o
futuro agendador, continua funcionando sem reautenticar. Para trocar o token, apague o arquivo.

Este módulo depende só do Starlette (sem FastAPI), para ser testável isoladamente.
Tudo é lido na hora do uso, não no import (padrão do projeto).
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from starlette.datastructures import Headers
from starlette.responses import HTMLResponse, JSONResponse

from connections.config import allowed_origins, backend_url, data_dir

TOKEN_HEADER = "X-Jarvis-Token"
TOKEN_FILE = "session_token"
BOOTSTRAP_PATH = "/session/bootstrap"
_MIN_TOKEN_LEN = 32

_cache: dict = {}  # path -> ((mtime_ns, size), token)


# ---- token -------------------------------------------------------------------

def token_path() -> Path:
    return data_dir() / TOKEN_FILE


def _create(path: Path) -> str:
    token = secrets.token_urlsafe(32)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)  # no Windows o chmod é parcial; a pasta do usuário já é privada
    except OSError:
        pass
    _cache.pop(path, None)
    return token


def get_token() -> str:
    """Token atual. Cria o arquivo na primeira vez ou se ele estiver apagado/corrompido."""
    path = token_path()
    try:
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
        hit = _cache.get(path)
        if hit and hit[0] == key:
            return hit[1]
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= _MIN_TOKEN_LEN:
            _cache[path] = (key, token)
            return token
    except FileNotFoundError:
        pass
    return _create(path)


def token_ok(candidate) -> bool:
    if not isinstance(candidate, str) or not candidate:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), get_token().encode("utf-8"))


# ---- Host e Origin ------------------------------------------------------------

def allowed_hosts() -> set[str]:
    """Valores aceitos no header Host: nomes locais na porta do backend."""
    parsed = urlparse(backend_url())
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    names = {"localhost", "127.0.0.1", "[::1]"}
    if parsed.hostname:
        names.add(parsed.hostname.lower())
    extra = {h.strip().lower() for h in (os.getenv("JARVIS_ALLOWED_HOSTS") or "").split(",") if h.strip()}
    hosts = {f"{n}:{port}" for n in names}
    if port in (80, 443):
        hosts |= names
    return hosts | extra


def host_ok(host: Optional[str]) -> bool:
    return bool(host) and host.strip().lower() in allowed_hosts()


def hud_origins() -> set[str]:
    """Origens do HUD: as configuradas + o próprio backend (que serve o HUD compilado)."""
    base = backend_url()
    extra = {base, base.replace("localhost", "127.0.0.1")}
    return {o.rstrip("/") for o in allowed_origins()} | extra


def origin_ok(origin: Optional[str]) -> bool:
    """Sem Origin (curl, testes, navegação direta) passa; com Origin, só se estiver na allowlist."""
    return not origin or origin.rstrip("/") in hud_origins()


# ---- HUD estático com o token embutido ---------------------------------------

def static_asset_checker(get_dist: Callable[[], Path], available: Callable[[], bool]) -> Callable[[str], bool]:
    """Diz se um caminho é arquivo do HUD compilado (público, sem token)."""

    def check(path: str) -> bool:
        if not available():
            return False
        dist = get_dist().resolve()
        if path in ("/", "/index.html"):
            return True
        try:
            p = (dist / path.lstrip("/")).resolve()
        except (OSError, ValueError):
            return False
        return p.is_file() and dist in p.parents

    return check


def index_with_token(dist: Path) -> HTMLResponse:
    """index.html do HUD com <meta name="jarvis-token">. Só é entregue a quem passou pelo
    guarda (Host e Origin válidos), e nunca fica em cache."""
    html = (dist / "index.html").read_text(encoding="utf-8")
    meta = f'<meta name="jarvis-token" content="{get_token()}">'
    html, n = re.subn(r"(<head[^>]*>)", lambda m: m.group(1) + meta, html, count=1, flags=re.I)
    if not n:
        html = meta + html
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# ---- middleware ASGI ----------------------------------------------------------

_CALLBACK = re.compile(r"^/auth/[^/]+/callback$")


class LocalGuardMiddleware:
    """Aplica Host + Origin + token em TODAS as rotas HTTP por padrão (rota nova já nasce protegida).

    Isentos do token (mas nunca do Host/Origin):
    - arquivos do HUD compilado (GET/HEAD);
    - /health;
    - /auth/<provedor>/callback, a volta do OAuth no navegador (protegida pelo `state`);
    - /session/bootstrap, que entrega o token ao HUD (dev, ou recuperação após troca do token) e exige
      Origin da allowlist ou Sec-Fetch-Site: same-origin.

    WebSocket: aqui só Host e Origin. O token vai na primeira mensagem (o navegador não consegue
    mandar header customizado), validada em voice/ws.py.
    """

    def __init__(self, app, public_static: Optional[Callable[[str], bool]] = None):
        self.app = app
        self.public_static = public_static or (lambda _path: False)

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")

        if kind == "websocket":
            if not host_ok(headers.get("host")) or not origin_ok(origin):
                await receive()  # evento websocket.connect
                await send({"type": "websocket.close", "code": 4403})
                return
            await self.app(scope, receive, send)
            return

        if not host_ok(headers.get("host")):
            await self._deny(scope, receive, send, 403, "Host não autorizado.")
            return
        if not origin_ok(origin):
            await self._deny(scope, receive, send, 403, "Origem não autorizada.")
            return

        method, path = scope["method"], scope["path"]

        if path == BOOTSTRAP_PATH and method == "GET":
            # Só um navegador abrindo o HUD chega aqui: ou de outra porta (modo dev, com Origin da
            # allowlist) ou da mesma origem (Sec-Fetch-Site, que a página não consegue forjar).
            # curl e outros programas sem nenhum dos dois são recusados.
            if not origin and headers.get("sec-fetch-site") != "same-origin":
                await self._deny(scope, receive, send, 403, "Origem não autorizada.")
                return
            resp = JSONResponse({"token": get_token()}, headers={"Cache-Control": "no-store"})
            await resp(scope, receive, send)
            return

        if self._is_public(method, path):
            await self.app(scope, receive, send)
            return

        if not token_ok(headers.get(TOKEN_HEADER)):
            await self._deny(scope, receive, send, 401, "Token de sessão ausente ou inválido.")
            return
        await self.app(scope, receive, send)

    def _is_public(self, method: str, path: str) -> bool:
        if method == "GET" and (path == "/health" or _CALLBACK.match(path)):
            return True
        return method in ("GET", "HEAD") and self.public_static(path)

    @staticmethod
    async def _deny(scope, receive, send, status: int, detail: str):
        resp = JSONResponse({"detail": detail}, status_code=status)
        await resp(scope, receive, send)
