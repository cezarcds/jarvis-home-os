import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from connections import db, oauth

from conftest import ORIGIN


def _id_token(email):
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"x.{payload}.y"


@pytest.fixture
def fake_google(monkeypatch):
    """Troca o cliente HTTP por um servidor OAuth falso e registra as chamadas."""
    calls = []
    behavior = {"refresh_error": None}

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        calls.append((str(request.url), {k: v[0] for k, v in form.items()}))
        if "revoke" in str(request.url):
            return httpx.Response(200)
        if form["grant_type"][0] == "authorization_code":
            return httpx.Response(200, json={
                "access_token": "AT-1", "refresh_token": "RT-1", "expires_in": 3600,
                "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
                "id_token": _id_token("eu@gmail.com"),
            })
        if behavior["refresh_error"]:
            return httpx.Response(400, json={"error": behavior["refresh_error"]})
        return httpx.Response(200, json={"access_token": "AT-2", "expires_in": 3600})

    monkeypatch.setattr(oauth, "client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return calls, behavior


def _configure(client, admin):
    client.put("/admin/providers/google/credentials", headers=admin,
               json={"client_id": "cid.apps.googleusercontent.com", "client_secret": "csecret"})


def _start(client):
    r = client.post("/auth/google/start", headers=ORIGIN)
    assert r.status_code == 200, r.text
    url = r.json()["authorize_url"]
    return url, {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_start_requires_credentials(client):
    r = client.post("/auth/google/start", headers=ORIGIN)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_configured"


def test_unknown_provider(client):
    assert client.post("/auth/facebook/start", headers=ORIGIN).status_code == 404
    assert client.get("/auth/facebook/callback?code=a&state=b").status_code == 400


def test_authorize_url_has_pkce_state_and_readonly_scopes(client, admin):
    _configure(client, admin)
    url, q = _start(client)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert q["code_challenge_method"] == "S256" and len(q["state"]) >= 32 and q["code_challenge"]
    assert q["redirect_uri"] == "http://localhost:8000/auth/google/callback"
    assert q["access_type"] == "offline"
    scopes = q["scope"].split()
    assert all("readonly" in s or s in ("openid", "email") for s in scopes)
    assert not any(s.endswith(("gmail.send", "gmail.modify", "mail.google.com/")) for s in scopes)


def test_full_flow_stores_encrypted_token_and_account(client, admin, fake_google):
    calls, _ = fake_google
    _configure(client, admin)
    _, q = _start(client)
    r = client.get("/auth/google/callback", params={"code": "CODE", "state": q["state"]})
    assert r.status_code == 200 and "eu@gmail.com" in r.text
    assert r.headers["cache-control"] == "no-store"
    # PKCE: o verifier enviado na troca bate com o challenge do início
    _, form = calls[0]
    expected = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert expected == q["code_challenge"]
    assert form["client_secret"] == "csecret" and form["redirect_uri"] == q["redirect_uri"]
    conn = db.get_connection("google")
    assert conn["account"] == "eu@gmail.com" and conn["token"]["refresh_token"] == "RT-1"
    listing = client.get("/connections").json()["connections"][0]
    assert {k: listing[k] for k in ("provider", "label", "status", "configured")} == {
        "provider": "google", "label": "Google", "status": "connected", "configured": True}
    assert listing["connected_at"] > 0
    assert "AT-1" not in client.get("/connections").text


def test_state_is_single_use_and_validated(client, admin, fake_google):
    _configure(client, admin)
    _, q = _start(client)
    assert client.get("/auth/google/callback", params={"code": "C", "state": "forjado"}).status_code == 400
    assert client.get("/auth/google/callback", params={"code": "C", "state": q["state"]}).status_code == 200
    # reutilizar o mesmo state falha
    assert client.get("/auth/google/callback", params={"code": "C", "state": q["state"]}).status_code == 400


def test_expired_state_is_rejected(client, admin, fake_google):
    _configure(client, admin)
    _, q = _start(client)
    oauth._pending[q["state"]].created = time.time() - oauth.STATE_TTL - 5
    assert client.get("/auth/google/callback", params={"code": "C", "state": q["state"]}).status_code == 400


def test_user_denied_consent(client, admin):
    _configure(client, admin)
    r = client.get("/auth/google/callback", params={"error": "access_denied"})
    assert r.status_code == 400 and "cancelada" in r.text.lower()
    assert db.get_connection("google") is None


def test_callback_page_escapes_provider_text(client):
    r = client.get("/auth/google/callback", params={"error": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in r.text


def test_access_token_auto_refresh(client, admin, fake_google):
    import asyncio
    calls, _ = fake_google
    _configure(client, admin)
    _, q = _start(client)
    client.get("/auth/google/callback", params={"code": "C", "state": q["state"]})

    assert asyncio.run(oauth.get_access_token("google")) == "AT-1"       # ainda válido, sem rede
    n = len(calls)
    conn = db.get_connection("google")
    conn["token"]["expires_at"] = time.time() + 10                          # quase expirando
    db.update_token("google", conn["token"])
    assert asyncio.run(oauth.get_access_token("google")) == "AT-2"
    assert len(calls) == n + 1
    assert db.get_connection("google")["token"]["refresh_token"] == "RT-1"  # mantém o refresh token


def test_invalid_grant_marks_reconnect(client, admin, fake_google):
    import asyncio
    _, behavior = fake_google
    _configure(client, admin)
    _, q = _start(client)
    client.get("/auth/google/callback", params={"code": "C", "state": q["state"]})
    conn = db.get_connection("google")
    conn["token"]["expires_at"] = 0
    db.update_token("google", conn["token"])
    behavior["refresh_error"] = "invalid_grant"
    with pytest.raises(oauth.ReconnectRequired):
        asyncio.run(oauth.get_access_token("google"))
    assert db.get_connection_public("google")["status"] == "reconnect"
    assert client.get("/connections").json()["connections"][0]["status"] == "reconnect"
    # continua exigindo reconexão sem bater na rede de novo
    with pytest.raises(oauth.ReconnectRequired):
        asyncio.run(oauth.get_access_token("google"))


def test_revoke_deletes_token_and_calls_provider(client, admin, fake_google):
    calls, _ = fake_google
    _configure(client, admin)
    _, q = _start(client)
    client.get("/auth/google/callback", params={"code": "C", "state": q["state"]})
    assert client.post("/connections/google/revoke", headers=admin).status_code == 200
    assert db.get_connection("google") is None
    assert any("revoke" in url and form["token"] == "RT-1" for url, form in calls)
    assert any(e["event"] == "oauth.revoked" for e in db.recent_audit())
