import os
import sqlite3
import stat

import pytest

from connections import crypto, db
from connections.config import data_dir


def test_encrypt_roundtrip_and_key_permissions():
    token = crypto.encrypt("segredo")
    assert token != "segredo" and "segredo" not in token
    assert crypto.decrypt(token) == "segredo"
    key = data_dir() / crypto.KEY_FILE
    assert key.exists()
    if os.name == "posix":
        assert stat.S_IMODE(key.stat().st_mode) == 0o600


def test_token_is_not_stored_in_plaintext():
    db.save_connection("google", {"access_token": "AT-visivel", "refresh_token": "RT-visivel", "expires_at": 1}, ["a"], "x@y.com")
    raw = sqlite3.connect(data_dir() / db.DB_FILE).execute("SELECT token_enc FROM connections").fetchone()[0]
    assert "AT-visivel" not in raw and "RT-visivel" not in raw
    assert db.get_connection("google")["token"]["refresh_token"] == "RT-visivel"
    assert "token" not in db.get_connection_public("google")


def test_settings_are_encrypted():
    db.set_setting("oauth.google.client_id", "meu-client-id")
    raw = sqlite3.connect(data_dir() / db.DB_FILE).execute("SELECT value FROM settings").fetchone()[0]
    assert "meu-client-id" not in raw
    assert db.get_setting("oauth.google.client_id") == "meu-client-id"


def test_wrong_key_cannot_decrypt(monkeypatch):
    db.set_setting("k", "v")
    monkeypatch.setenv("JARVIS_SECRET_KEY", "5E_Ea1fQ6o6EuLQ0r4mFqgm7S0uJ0pK3o4i0m3m1xYk=")
    with pytest.raises(crypto.DecryptError):
        db.get_setting("k")


def test_data_dir_inside_git_repo_is_refused(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(repo / "dados"))
    with pytest.raises(RuntimeError):
        data_dir()
