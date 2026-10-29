from connections import admin_auth, db

from conftest import ORIGIN


def test_setup_login_flow(client):
    assert client.get("/admin/status", headers=ORIGIN).json() == {"password_set": False, "authenticated": False}
    assert client.post("/admin/setup", json={"password": "curta"}, headers=ORIGIN).status_code == 400
    r = client.post("/admin/setup", json={"password": "senha-forte-123"}, headers=ORIGIN)
    assert r.status_code == 200
    token = r.json()["token"]
    # segunda definição é recusada
    assert client.post("/admin/setup", json={"password": "outra-senha-123"}, headers=ORIGIN).status_code == 409
    assert client.post("/admin/login", json={"password": "errada-errada"}, headers=ORIGIN).status_code == 401
    ok = client.post("/admin/login", json={"password": "senha-forte-123"}, headers=ORIGIN)
    assert ok.status_code == 200
    status = client.get("/admin/status", headers={**ORIGIN, "X-Jarvis-Admin": token}).json()
    assert status["authenticated"] is True


def test_password_is_hashed_not_stored(client):
    client.post("/admin/setup", json={"password": "senha-forte-123"}, headers=ORIGIN)
    stored = db.get_setting(admin_auth.PASSWORD_KEY)
    assert stored.startswith("$2") and "senha-forte-123" not in stored


def test_lockout_after_repeated_failures(client):
    client.post("/admin/setup", json={"password": "senha-forte-123"}, headers=ORIGIN)
    codes = [client.post("/admin/login", json={"password": "x" * 9}, headers=ORIGIN).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # mesmo a senha certa fica bloqueada durante a janela
    assert client.post("/admin/login", json={"password": "senha-forte-123"}, headers=ORIGIN).status_code == 429


def test_admin_routes_require_token(client):
    valid_body = {"client_id": "abcde-12345"}   # corpo válido: o 401 não depende da ordem de validação
    for method, path in [("get", "/admin/overview"), ("put", "/admin/providers/google/credentials"),
                         ("put", "/admin/providers/google/scopes"), ("post", "/connections/google/revoke")]:
        kwargs = {"json": valid_body if "credentials" in path else {"scopes": []}} if method == "put" else {}
        r = getattr(client, method)(path, headers=ORIGIN, **kwargs)
        assert r.status_code == 401, path


def test_foreign_origin_is_blocked_even_with_valid_token(client, admin):
    evil = {**admin, "Origin": "https://site-malicioso.example"}
    assert client.get("/admin/overview", headers=evil).status_code == 403
    assert client.post("/connections/google/revoke", headers=evil).status_code == 403
    assert client.post("/auth/google/start", headers={"Origin": "https://site-malicioso.example"}).status_code == 403


def test_logout_invalidates_token(client, admin):
    assert client.post("/admin/logout", headers=admin).status_code == 200
    assert client.get("/admin/overview", headers=admin).status_code == 401


def test_credentials_and_scopes(client, admin):
    r = client.put("/admin/providers/google/credentials", headers=admin,
                   json={"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "GOCSPX-segredo"})
    assert r.status_code == 200
    ov = client.get("/admin/overview", headers=admin).json()
    google = ov["providers"][0]
    assert google["configured"] is True and google["credentials_source"] == "admin"
    assert "GOCSPX-segredo" not in str(ov)                      # o secret nunca volta
    assert google["redirect_uri"] == "http://localhost:8000/auth/google/callback"
    # allowlist de escopos
    assert client.put("/admin/providers/google/scopes", headers=admin,
                      json={"scopes": ["https://mail.google.com/"]}).status_code == 400
    assert client.put("/admin/providers/google/scopes", headers=admin,
                      json={"scopes": ["https://www.googleapis.com/auth/youtube.readonly"]}).status_code == 200
    ov = client.get("/admin/overview", headers=admin).json()
    assert any(o["enabled"] for o in ov["providers"][0]["optional_scopes"])
    assert any(e["event"] == "admin.credentials_set" for e in ov["audit"])
