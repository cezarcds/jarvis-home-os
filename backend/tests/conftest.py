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
    for var in ("JARVIS_SECRET_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
                "GROQ_API_KEY", "GEMINI_API_KEY", "JARVIS_ALLOWED_ORIGINS"):
        monkeypatch.delenv(var, raising=False)
    from connections import admin_auth, oauth
    admin_auth.reset_state()
    oauth._pending.clear()
    oauth._refresh_locks.clear()
    from actions import handler
    handler.reset_state()  # sessões de visão não vazam entre testes
    yield
    handler.reset_state()


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(main, "GROQ_API_KEY", "")
    monkeypatch.setattr(main, "GEMINI_API_KEY", "")
    return TestClient(main.app)


ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture
def admin(client):
    """Cliente com senha definida e sessão de admin; devolve (headers com token)."""
    r = client.post("/admin/setup", json={"password": "senha-forte-123"}, headers=ORIGIN)
    assert r.status_code == 200
    return {**ORIGIN, "X-Jarvis-Admin": r.json()["token"]}
