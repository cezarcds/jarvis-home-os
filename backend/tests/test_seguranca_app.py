"""Fase 0 — o app real (main.py) exige token, Host e Origin em todas as rotas HTTP e no WebSocket."""
import pytest
from starlette.websockets import WebSocketDisconnect

from security import session

ORIGEM_HUD = {"Origin": "http://localhost:5173"}
ORIGEM_ESTRANHA = {"Origin": "https://site-malicioso.example"}
# O TestClient manda Host "testserver" em WebSocket, ignorando o base_url (navegador de verdade manda o certo).
WS_HUD = {"Host": "localhost:8000", **ORIGEM_HUD}
WS_ESTRANHA = {"Host": "localhost:8000", **ORIGEM_ESTRANHA}

# Rotas HTTP do app que precisam de token (método, caminho).
ROTAS_PROTEGIDAS = [
    ("get", "/connections"),
    ("get", "/admin/status"),
    ("post", "/admin/login"),
    ("post", "/auth/google/start"),
    ("get", "/v1/routines"),
    ("get", "/v1/tools"),
    ("post", "/v1/assistant"),
    ("post", "/v1/chat/completions"),
    ("post", "/v1/scene"),
    ("get", "/v1/media/search"),
    ("get", "/v1/media/diagnose"),
    ("get", "/v1/actions/apps"),
    ("get", "/v1/actions/windows"),
    ("get", "/v1/voice/status"),
    ("get", "/v1/gate/pendentes"),
    ("post", "/v1/gate/parar"),
    ("post", "/v1/gate/abc12345/confirmar"),
    ("post", "/v1/gate/abc12345/negar"),
    ("get", "/v1/tarefas"),
    ("get", "/v1/tarefas/estado"),
    ("post", "/v1/tarefas/importar"),
    ("post", "/v1/tarefas/agendador/pausar"),
    ("post", "/v1/tarefas/x/executar"),
]


@pytest.mark.parametrize("metodo,caminho", ROTAS_PROTEGIDAS)
def test_rota_sem_token_e_rejeitada(anonimo, metodo, caminho):
    assert getattr(anonimo, metodo)(caminho).status_code == 401


@pytest.mark.parametrize("metodo,caminho", ROTAS_PROTEGIDAS)
def test_rota_com_origin_estranha_e_rejeitada_mesmo_com_token(anonimo, metodo, caminho):
    headers = {**ORIGEM_ESTRANHA, session.TOKEN_HEADER: session.get_token()}
    assert getattr(anonimo, metodo)(caminho, headers=headers).status_code == 403


def test_com_token_a_rota_funciona(client):
    assert client.get("/v1/voice/status").status_code == 200
    assert client.get("/v1/tools").status_code == 200


def test_health_continua_publico(anonimo):
    assert anonimo.get("/health").status_code == 200


def test_recusa_401_leva_headers_cors_para_o_hud_ler(anonimo):
    """O CORS é o middleware mais externo: sem isto o HUD veria só 'erro de rede', não o 401."""
    r = anonimo.get("/v1/tools", headers=ORIGEM_HUD)
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_preflight_do_hud_funciona_sem_token(anonimo):
    r = anonimo.options("/v1/assistant", headers={
        **ORIGEM_HUD, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-jarvis-token"})
    assert r.status_code == 200


def test_openapi_e_docs_tambem_exigem_token(anonimo):
    assert anonimo.get("/openapi.json").status_code == 401
    assert anonimo.get("/docs").status_code == 401


def test_host_estranho_e_recusado(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app, base_url="http://rebind.example:8000",
                   headers={session.TOKEN_HEADER: session.get_token()})
    assert c.get("/v1/tools").status_code == 403


def test_callback_oauth_chega_ao_handler_sem_token(anonimo):
    """A volta do Google é uma navegação do navegador: não carrega header. Quem protege é o `state`."""
    r = anonimo.get("/auth/google/callback?code=x&state=invalido")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


# ---- WebSocket de voz -----------------------------------------------------------

def test_ws_com_origin_estranha_fecha_4403(anonimo):
    with pytest.raises(WebSocketDisconnect) as exc:
        with anonimo.websocket_connect("/v1/voice/ws", headers=WS_ESTRANHA):
            pass
    assert exc.value.code == 4403


def test_ws_sem_mensagem_de_auth_fecha_4401(anonimo, monkeypatch):
    from voice import ws as voice_ws
    monkeypatch.setattr(voice_ws, "AUTH_TIMEOUT_S", 0.2)
    with anonimo.websocket_connect("/v1/voice/ws", headers=WS_HUD) as sock:
        with pytest.raises(WebSocketDisconnect) as exc:
            sock.receive_json()
    assert exc.value.code == 4401


@pytest.mark.parametrize("primeira", [
    {"type": "auth", "token": "errado"},
    {"type": "auth"},
    {"type": "mute", "value": True},  # mensagem qualquer antes do auth
])
def test_ws_com_auth_invalido_fecha_4401(anonimo, primeira):
    with anonimo.websocket_connect("/v1/voice/ws", headers=WS_HUD) as sock:
        sock.send_json(primeira)
        with pytest.raises(WebSocketDisconnect) as exc:
            sock.receive_json()
    assert exc.value.code == 4401


def test_ws_com_token_correto_segue_adiante(anonimo, monkeypatch):
    from voice import stt
    monkeypatch.setattr(stt, "available", lambda: (False, "Whisper indisponível no teste."))
    with anonimo.websocket_connect("/v1/voice/ws", headers=WS_HUD) as sock:
        sock.send_json({"type": "auth", "token": session.get_token()})
        msg = sock.receive_json()
    assert msg["type"] == "error" and msg["code"] == "unavailable"  # passou da autenticação


# ---- HUD compilado ----------------------------------------------------------------

def test_hud_compilado_recebe_o_token_no_index(tmp_path, monkeypatch):
    """Com frontend/dist presente, '/' é público e traz o token; o resto do app continua fechado."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.testclient import TestClient

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><head></head><body>HUD</body></html>", encoding="utf-8")
    (dist / "assets" / "a.js").write_text("1", encoding="utf-8")

    app = FastAPI()
    app.add_middleware(session.LocalGuardMiddleware,
                       public_static=session.static_asset_checker(lambda: dist, lambda: True))

    @app.get("/")
    async def index():
        return session.index_with_token(dist)

    @app.get("/v1/segredo")
    async def segredo():
        return {"x": 1}

    app.mount("/", StaticFiles(directory=dist, html=True), name="hud")
    c = TestClient(app, base_url="http://localhost:8000")

    r = c.get("/")
    assert r.status_code == 200 and session.get_token() in r.text
    assert c.get("/assets/a.js").status_code == 200
    assert c.get("/v1/segredo").status_code == 401
