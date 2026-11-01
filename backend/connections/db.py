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


# Colunas da auditoria estruturada de ações (Fase 1). São nulas nas linhas antigas (admin, OAuth),
# então o painel admin e recent_audit() continuam funcionando sem mudança.
AUDIT_ACTION_COLUMNS = {
    "run_id": "TEXT", "tool": "TEXT", "nivel": "INTEGER", "params": "TEXT", "resultado": "TEXT",
    "confirmacao": "TEXT", "sessao": "TEXT", "contaminado": "INTEGER", "duracao_ms": "INTEGER", "origem": "TEXT",
}
_migrated: set[str] = set()


def _migrate(conn: sqlite3.Connection, path) -> None:
    """Acrescenta as colunas que faltam em audit_log (bancos criados antes da Fase 1). Só roda
    uma vez por arquivo de banco em cada execução do programa."""
    key = str(path)
    if key in _migrated:
        return
    have = {r["name"] for r in conn.execute("PRAGMA table_info(audit_log)")}
    for col, typ in AUDIT_ACTION_COLUMNS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {typ}")
    conn.commit()
    _migrated.add(key)


def connect() -> sqlite3.Connection:
    path = data_dir() / DB_FILE
    new = not path.exists()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn, path)
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


def audit_action(*, run_id: str, tool: str, nivel: int, resultado: str, params: Any = None,
                 confirmacao: str = "nenhuma", sessao: str = "", contaminado: bool = False,
                 duracao_ms: int | None = None, origem: str = "", detalhe: str = "") -> None:
    """Registro estruturado de uma decisão ou execução do gate. `params` já deve vir redigido
    (actions.redact.redigir); aqui só é serializado."""
    payload = json.dumps(params, ensure_ascii=False, default=str)[:2000] if params is not None else None
    with closing(connect()) as c, c:
        c.execute(
            "INSERT INTO audit_log(ts,event,detail,run_id,tool,nivel,params,resultado,confirmacao,sessao,"
            "contaminado,duracao_ms,origem) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), f"acao.{resultado}", detalhe[:500], run_id, tool, nivel, payload, resultado,
             confirmacao, sessao, int(bool(contaminado)), duracao_ms, origem),
        )


def recent_actions(limit: int = 50) -> list[dict[str, Any]]:
    with closing(connect()) as c:
        rows = c.execute(
            "SELECT id,ts,run_id,tool,nivel,params,resultado,confirmacao,sessao,contaminado,duracao_ms,origem,detail "
            "FROM audit_log WHERE tool IS NOT NULL ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
