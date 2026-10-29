"""Banco SQLite local: configurações, conexões (tokens) e log de auditoria.
Todo valor sensível é gravado criptografado."""
import json
import os
import sqlite3
import time
from contextlib import closing
from typing import Any, Optional

from .config import data_dir
from .crypto import decrypt, encrypt

DB_FILE = "jarvis.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS connections (
    provider TEXT PRIMARY KEY,
    account TEXT,
    scopes TEXT NOT NULL DEFAULT '[]',
    token_enc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'connected',
    created_at REAL NOT NULL,
    last_sync REAL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    event TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
"""


def connect() -> sqlite3.Connection:
    path = data_dir() / DB_FILE
    new = not path.exists()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if new:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return conn


# ---- configurações (sempre criptografadas) ----------------------------------

def set_setting(key: str, value: str) -> None:
    with closing(connect()) as c, c:
        c.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, encrypt(value), time.time()),
        )


def get_setting(key: str) -> Optional[str]:
    with closing(connect()) as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return decrypt(row["value"]) if row else None


def delete_setting(key: str) -> None:
    with closing(connect()) as c, c:
        c.execute("DELETE FROM settings WHERE key=?", (key,))


# ---- conexões ---------------------------------------------------------------

def save_connection(provider: str, token: dict[str, Any], scopes: list[str], account: Optional[str]) -> None:
    with closing(connect()) as c, c:
        c.execute(
            "INSERT INTO connections(provider,account,scopes,token_enc,status,created_at) "
            "VALUES(?,?,?,?, 'connected', ?) "
            "ON CONFLICT(provider) DO UPDATE SET account=excluded.account, scopes=excluded.scopes, "
            "token_enc=excluded.token_enc, status='connected', created_at=excluded.created_at",
            (provider, account, json.dumps(scopes), encrypt(json.dumps(token)), time.time()),
        )


def get_connection(provider: str) -> Optional[dict[str, Any]]:
    with closing(connect()) as c:
        row = c.execute("SELECT * FROM connections WHERE provider=?", (provider,)).fetchone()
    if not row:
        return None
    return {
        "provider": row["provider"],
        "account": row["account"],
        "scopes": json.loads(row["scopes"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "last_sync": row["last_sync"],
        "token": json.loads(decrypt(row["token_enc"])),
    }


def get_connection_public(provider: str) -> Optional[dict[str, Any]]:
    """Mesmos dados de get_connection, sem o token (nem descriptografa)."""
    with closing(connect()) as c:
        row = c.execute(
            "SELECT provider,account,scopes,status,created_at,last_sync FROM connections WHERE provider=?",
            (provider,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["scopes"] = json.loads(d["scopes"])
    return d


def update_token(provider: str, token: dict[str, Any]) -> None:
    with closing(connect()) as c, c:
        c.execute("UPDATE connections SET token_enc=?, status='connected' WHERE provider=?",
                  (encrypt(json.dumps(token)), provider))


def mark_status(provider: str, status: str) -> None:
    with closing(connect()) as c, c:
        c.execute("UPDATE connections SET status=? WHERE provider=?", (status, provider))


def touch_sync(provider: str) -> None:
    with closing(connect()) as c, c:
        c.execute("UPDATE connections SET last_sync=? WHERE provider=?", (time.time(), provider))


def delete_connection(provider: str) -> None:
    with closing(connect()) as c, c:
        c.execute("DELETE FROM connections WHERE provider=?", (provider,))


# ---- auditoria --------------------------------------------------------------

def audit(event: str, detail: str = "") -> None:
    with closing(connect()) as c, c:
        c.execute("INSERT INTO audit_log(ts,event,detail) VALUES(?,?,?)", (time.time(), event, detail[:500]))


def recent_audit(limit: int = 20) -> list[dict[str, Any]]:
    with closing(connect()) as c:
        rows = c.execute("SELECT ts,event,detail FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
