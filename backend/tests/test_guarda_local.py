"""Fase 0 — guarda das rotas locais (Host, Origin, token), testada num app Starlette mínimo.
Não depende de FastAPI nem do main.py: só da lógica de security/session.py."""
import os
import stat
import sys

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from security import session

HUD_ORIGIN = {"Origin": "http://localhost:5173"}
HOST = "http://localhost:8000"
# O TestClient manda Host "testserver" em WebSocket, ignorando o base_url (navegador de verdade manda o certo).
WS_HOST = {"Host": "localhost:8000"}


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JARVIS_BACKEND_URL", "http://localhost:8000")
    monkeypatch.delenv("JARVIS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("JARVIS_ALLOWED_HOSTS", raising=False)
    session._cache.clear()


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><html><head><title>J</title></head><body></body></html>", encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("nao pode vazar", encoding="utf-8")
    return d


def _app(dist):
    async def eco(request):
        return JSONResponse({"ok": True})

    async def health(request):
        return JSONResponse({"status": "ok"})

    async def callback(request):
        return PlainTextResponse("callback")

    async def index(request):
        return session.index_with_token(dist)

    async def ws(websocket):
        await websocket.accept()
        await websocket.send_json({"type": "ola"})
        await websocket.close()

    app = Starlette(routes=[
        Route("/v1/assistant", eco, methods=["GET", "POST"]),
        Route("/health", health),
        Route("/auth/{provider}/callback", callback),
        Route("/", index),
        Route("/assets/app.js", eco),
        WebSocketRoute("/v1/voice/ws", ws),
    ])
    app.add_middleware(
        session.LocalGuardMiddleware,
        public_static=session.static_asset_checker(lambda: dist, lambda: True),
    )
    return app


@pytest.fixture
def anonimo(dist):
    return TestClient(_app(dist), base_url=HOST)


@pytest.fixture
def com_token(dist):
    return TestClient(_app(dist), base_url=HOST, headers={session.TOKEN_HEADER: session.get_token()})


# ---- token -----------------------------------------------------------------

def test_sem_token_401(anonimo):
    r = anonimo.post("/v1/assistant", json={})
    assert r.status_code == 401


def test_token_errado_401(anonimo):
    r = anonimo.post("/v1/assistant", json={}, headers={session.TOKEN_HEADER: "x" * 43})
    assert r.status_code == 401


def test_token_correto_passa(com_token):
    assert com_token.post("/v1/assistant", json={}).status_code == 200


def test_token_vazio_ou_curto_401(anonimo):
    for valor in ("", " ", "abc"):
        assert anonimo.post("/v1/assistant", headers={session.TOKEN_HEADER: valor}).status_code == 401


def test_rota_nova_nasce_protegida(dist):
    """Rota que ninguém lembrou de proteger continua exigindo token (guarda é por padrão)."""
    async def nova(request):
        return JSONResponse({"x": 1})

    app = Starlette(routes=[Route("/v1/coisa-nova", nova, methods=["GET", "POST", "PUT", "DELETE"])])
    app.add_middleware(session.LocalGuardMiddleware)
    c = TestClient(app, base_url=HOST)
    for m in ("get", "post", "put", "delete"):
        assert getattr(c, m)("/v1/coisa-nova").status_code == 401


# ---- Origin e Host ---------------------------------------------------------

def test_origin_estranha_403_mesmo_com_token_certo(com_token):
    r = com_token.post("/v1/assistant", json={}, headers={"Origin": "https://site-malicioso.example"})
    assert r.status_code == 403


def test_origin_do_hud_com_token_passa(com_token):
    assert com_token.post("/v1/assistant", json={}, headers=HUD_ORIGIN).status_code == 200


def test_host_estranho_403_mesmo_com_token_certo(dist):
    """DNS rebinding: o navegador acha que está em outro-site.example, mas o IP é 127.0.0.1."""
    c = TestClient(_app(dist), base_url="http://outro-site.example:8000",
                   headers={session.TOKEN_HEADER: session.get_token()})
    assert c.post("/v1/assistant", json={}).status_code == 403


def test_host_com_porta_errada_403(dist):
    c = TestClient(_app(dist), base_url="http://localhost:9999",
                   headers={session.TOKEN_HEADER: session.get_token()})
    assert c.get("/v1/assistant").status_code == 403


def test_127_0_0_1_na_porta_certa_passa(dist):
    c = TestClient(_app(dist), base_url="http://127.0.0.1:8000",
                   headers={session.TOKEN_HEADER: session.get_token()})
    assert c.get("/v1/assistant").status_code == 200


def test_host_e_checado_ate_nas_rotas_publicas(dist):
    c = TestClient(_app(dist), base_url="http://outro-site.example:8000")
    assert c.get("/health").status_code == 403
    assert c.get("/").status_code == 403


# ---- isenções --------------------------------------------------------------

def test_health_e_callback_oauth_sao_publicos(anonimo):
    assert anonimo.get("/health").status_code == 200
    assert anonimo.get("/auth/google/callback?code=a&state=b").status_code == 200


def test_isencao_e_so_para_get(anonimo):
    assert anonimo.post("/health").status_code == 401
    assert anonimo.post("/auth/google/callback").status_code == 401


def test_callback_com_origin_estranha_continua_bloqueado(anonimo):
    r = anonimo.get("/auth/google/callback", headers={"Origin": "https://site-malicioso.example"})
    assert r.status_code == 403


# ---- HUD estático e bootstrap ------------------------------------------------

def test_hud_e_publico_e_traz_o_token(anonimo):
    r = anonimo.get("/")
    assert r.status_code == 200
    assert f'<meta name="jarvis-token" content="{session.get_token()}">' in r.text
    assert "no-store" in r.headers["cache-control"]


def test_asset_do_hud_e_publico(anonimo):
    assert anonimo.get("/assets/app.js").status_code == 200


def test_arquivo_fora_do_dist_nao_e_publico(anonimo):
    for caminho in ("/../segredo.txt", "/assets/../../segredo.txt", "/%2e%2e/segredo.txt"):
        assert anonimo.get(caminho).status_code in (401, 404)


def test_bootstrap_exige_origin_da_allowlist(anonimo):
    assert anonimo.get(session.BOOTSTRAP_PATH).status_code == 403  # sem Origin
    assert anonimo.get(session.BOOTSTRAP_PATH, headers={"Origin": "https://site-malicioso.example"}).status_code == 403
    r = anonimo.get(session.BOOTSTRAP_PATH, headers=HUD_ORIGIN)
    assert r.status_code == 200 and r.json() == {"token": session.get_token()}


def test_bootstrap_na_mesma_origem_usa_sec_fetch_site(anonimo):
    """HUD compilado: GET da mesma origem não manda Origin, mas o navegador manda Sec-Fetch-Site."""
    r = anonimo.get(session.BOOTSTRAP_PATH, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200 and r.json() == {"token": session.get_token()}
    assert anonimo.get(session.BOOTSTRAP_PATH, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert anonimo.get(session.BOOTSTRAP_PATH, headers={"Sec-Fetch-Site": "same-site"}).status_code == 403


# ---- WebSocket ---------------------------------------------------------------

def test_websocket_origin_estranha_fecha_com_4403(anonimo):
    with pytest.raises(WebSocketDisconnect) as exc:
        with anonimo.websocket_connect("/v1/voice/ws", headers={**WS_HOST, "Origin": "https://site-malicioso.example"}):
            pass
    assert exc.value.code == 4403


def test_websocket_host_estranho_fecha_com_4403(dist):
    c = TestClient(_app(dist), base_url="http://outro-site.example:8000")
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/v1/voice/ws", headers={"Host": "outro-site.example:8000"}):
            pass
    assert exc.value.code == 4403


def test_websocket_origin_do_hud_passa_pelo_guarda(anonimo):
    with anonimo.websocket_connect("/v1/voice/ws", headers={**WS_HOST, **HUD_ORIGIN}) as ws:
        assert ws.receive_json() == {"type": "ola"}


# ---- arquivo do token ----------------------------------------------------------

def test_token_persiste_entre_chamadas_e_reinicios():
    primeiro = session.get_token()
    session._cache.clear()  # simula o backend reiniciando: só o arquivo sobrevive
    assert session.get_token() == primeiro
    assert len(primeiro) >= 32


def test_token_fica_em_arquivo_privado():
    session.get_token()
    p = session.token_path()
    assert p.exists() and p.parent.name == "data"
    if os.name != "nt":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_apagar_o_arquivo_troca_o_token():
    antigo = session.get_token()
    session.token_path().unlink()
    novo = session.get_token()
    assert novo != antigo
    assert not session.token_ok(antigo) and session.token_ok(novo)


def test_arquivo_corrompido_vira_token_novo():
    session.get_token()
    session.token_path().write_text("curto", encoding="utf-8")
    novo = session.get_token()
    assert len(novo) >= 32 and novo != "curto"


def test_token_ok_rejeita_tipos_estranhos():
    for v in (None, "", 123, b"x", ["a"], "ção" * 20):
        assert session.token_ok(v) is False


def test_token_dentro_de_repositorio_e_recusado(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(repo / "dados"))
    with pytest.raises(RuntimeError):
        session.get_token()
