import os
import sys
from pathlib import Path

import dotenv
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# O main.py chama load_dotenv(override=True). Os testes nunca podem ler o .env real
# (chaves de verdade => chamadas pagas aos provedores de IA), então neutralizamos antes do import.
dotenv.load_dotenv = lambda *args, **kwargs: False


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Cada teste usa uma pasta de dados nova e nenhuma chave de IA real."""
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JARVIS_BACKEND_URL", "http://localhost:8000")
    monkeypatch.setenv("JARVIS_SCHEDULER", "0")  # o agendador não liga nos testes
    for var in ("JARVIS_SECRET_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
                "GROQ_API_KEY", "GEMINI_API_KEY", "JARVIS_ALLOWED_ORIGINS"):
        monkeypatch.delenv(var, raising=False)
    from connections import admin_auth, oauth
    admin_auth.reset_state()
    oauth._pending.clear()
    oauth._refresh_locks.clear()
    from actions import gate, handler
    from connections import db
    from tarefas import executor as tarefas_executor, store as tarefas_store
    handler.reset_state()  # sessões de visão não vazam entre testes
    gate.reset_state()     # pendentes, contaminação e parada também não
    db._migrated.clear()
    tarefas_store.reset_state()
    tarefas_executor._rodando.clear()
    yield
    handler.reset_state()
    gate.reset_state()


def _local_client_class():
    from fastapi.testclient import TestClient

    class LocalClient(TestClient):
        """Cliente que age como o HUD: Host localhost:8000 e o token de sessão em todo pedido.
        O token é lido na hora do pedido, porque cada teste usa uma pasta de dados nova."""

        def __init__(self, app, **kw):
            kw.setdefault("base_url", "http://localhost:8000")
            super().__init__(app, **kw)

        def request(self, *args, **kw):
            from security import session

            headers = dict(kw.pop("headers", None) or {})
            headers.setdefault(session.TOKEN_HEADER, session.get_token())
            return super().request(*args, headers=headers, **kw)

    return LocalClient


def LocalClient(app, **kw):  # noqa: N802 - usado como classe nos testes
    return _local_client_class()(app, **kw)


@pytest.fixture
def client(monkeypatch):
    import main
    monkeypatch.setattr(main, "GROQ_API_KEY", "")
    monkeypatch.setattr(main, "GEMINI_API_KEY", "")
    return LocalClient(main.app)


@pytest.fixture
def anonimo(monkeypatch):
    """Cliente sem token (como outro site ou um processo qualquer da máquina), com Host válido."""
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(main, "GROQ_API_KEY", "")
    monkeypatch.setattr(main, "GEMINI_API_KEY", "")
    return TestClient(main.app, base_url="http://localhost:8000")


ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture
def admin(client):
    """Cliente com senha definida e sessão de admin; devolve (headers com token)."""
    r = client.post("/admin/setup", json={"password": "senha-forte-123"}, headers=ORIGIN)
    assert r.status_code == 200
    return {**ORIGIN, "X-Jarvis-Admin": r.json()["token"]}
