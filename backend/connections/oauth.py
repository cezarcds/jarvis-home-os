"""OAuth 2.0 (código de autorização + PKCE + state) feito direto com httpx."""
import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx

from . import db
from .config import backend_url
from .providers import ProviderSpec, get_provider

log = logging.getLogger("jarvis.connections")

STATE_TTL = 600  # segundos para o usuário concluir a autorização


class OAuthError(Exception):
    """Falha de autenticação. A mensagem é segura para mostrar ao usuário."""


class NotConfigured(OAuthError):
    pass


class ReconnectRequired(OAuthError):
    """O refresh token foi recusado (invalid_grant): o usuário precisa autorizar de novo."""


def client_factory() -> httpx.AsyncClient:
    """Ponto único de criação do cliente HTTP (os testes trocam por um transporte falso)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0))


@dataclass
class _Pending:
    provider: str
    verifier: str
    created: float


_pending: dict[str, _Pending] = {}
_refresh_locks: dict[str, asyncio.Lock] = {}


# ---- credenciais ------------------------------------------------------------

def get_credentials(spec: ProviderSpec) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Retorna (client_id, client_secret, origem). O admin tem prioridade sobre o ambiente."""
    cid = db.get_setting(f"oauth.{spec.id}.client_id")
    if cid:
        return cid, db.get_setting(f"oauth.{spec.id}.client_secret"), "admin"
    cid = os.getenv(spec.env_client_id, "").strip() if spec.env_client_id else ""
    if cid:
        secret = os.getenv(spec.env_client_secret, "").strip() or None
        return cid, secret, "env"
    return None, None, None


def is_configured(spec: ProviderSpec) -> bool:
    return get_credentials(spec)[0] is not None


def redirect_uri(spec: ProviderSpec) -> str:
    return f"{backend_url()}/auth/{spec.id}/callback"


def enabled_scopes(spec: ProviderSpec) -> list[str]:
    extra: list[str] = []
    raw = db.get_setting(f"scopes.{spec.id}")
    if raw:
        extra = [s for s in json.loads(raw) if s in spec.optional_scopes]
    return list(spec.base_scopes) + extra


# ---- fluxo de autorização ---------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _purge_expired() -> None:
    now = time.time()
    for s in [s for s, p in _pending.items() if now - p.created > STATE_TTL]:
        del _pending[s]


def begin(provider_id: str) -> str:
    spec = get_provider(provider_id)
    if not spec:
        raise OAuthError("Provedor desconhecido.")
    client_id, _, _ = get_credentials(spec)
    if not client_id:
        raise NotConfigured(f"Falta o Client ID do {spec.label}. Configure no painel de administração.")
    _purge_expired()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    _pending[state] = _Pending(spec.id, verifier, time.time())
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(spec),
        "response_type": "code",
        "scope": " ".join(enabled_scopes(spec)),
        "state": state,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode("ascii")).digest()),
        "code_challenge_method": "S256",
        **spec.extra_auth_params,
    }
    db.audit("oauth.begin", spec.id)
    return f"{spec.auth_url}?{urlencode(params)}"


def _email_from_id_token(id_token: Optional[str]) -> Optional[str]:
    """Só para rotular a conta no admin. O token veio direto do endpoint do provedor
    por TLS, então não é verificado de novo aqui e NÃO é usado para decisões de segurança."""
    if not id_token:
        return None
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("email")
    except Exception:
        return None


async def finish(provider_id: str, code: str, state: str) -> str:
    """Troca o código pelos tokens e grava no cofre. Retorna o rótulo da conta."""
    _purge_expired()
    pending = _pending.pop(state, None)
    if not pending or pending.provider != provider_id:
        raise OAuthError("Solicitação inválida ou expirada. Tente conectar de novo.")
    spec = get_provider(provider_id)
    client_id, client_secret, _ = get_credentials(spec)  # type: ignore[arg-type]
    if not client_id:
        raise NotConfigured("Credenciais ausentes.")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(spec),  # type: ignore[arg-type]
        "client_id": client_id,
        "code_verifier": pending.verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with client_factory() as client:
        resp = await client.post(spec.token_url, data=data)  # type: ignore[union-attr]
    if resp.is_error:
        log.warning("Troca de código falhou (%s): HTTP %s %s", provider_id, resp.status_code, resp.text[:200])
        db.audit("oauth.exchange_failed", f"{provider_id} HTTP {resp.status_code}")
        raise OAuthError("O provedor recusou a autorização.")
    body = resp.json()
    token = {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token"),
        "expires_at": time.time() + int(body.get("expires_in", 3600)),
        "token_type": body.get("token_type", "Bearer"),
    }
    previous = db.get_connection(provider_id)
    if not token["refresh_token"] and previous:
        token["refresh_token"] = previous["token"].get("refresh_token")
    scopes = (body.get("scope") or " ".join(enabled_scopes(spec))).split()  # type: ignore[arg-type]
    account = _email_from_id_token(body.get("id_token"))
    db.save_connection(provider_id, token, scopes, account)
    db.audit("oauth.connected", f"{provider_id} {account or ''}".strip())
    if not token["refresh_token"]:
        log.warning("%s não devolveu refresh_token; a conexão vai exigir login ao expirar.", provider_id)
    return account or spec.label  # type: ignore[union-attr]


# ---- uso dos tokens ---------------------------------------------------------

async def get_access_token(provider_id: str) -> str:
    """Devolve um access token válido, renovando sozinho quando faltar menos de 60s."""
    conn = db.get_connection(provider_id)
    if not conn or conn["status"] == "disconnected":
        raise OAuthError("Conta não conectada.")
    if conn["status"] == "reconnect":
        raise ReconnectRequired("A conexão expirou. Autorize novamente.")
    token = conn["token"]
    if token["expires_at"] - 60 > time.time():
        return token["access_token"]
    lock = _refresh_locks.setdefault(provider_id, asyncio.Lock())
    async with lock:
        conn = db.get_connection(provider_id)  # outro pedido pode ter renovado enquanto esperávamos
        token = conn["token"] if conn else token
        if token["expires_at"] - 60 > time.time():
            return token["access_token"]
        return await _refresh(provider_id, token)


async def _refresh(provider_id: str, token: dict) -> str:
    spec = get_provider(provider_id)
    client_id, client_secret, _ = get_credentials(spec)  # type: ignore[arg-type]
    refresh_token = token.get("refresh_token")
    if not refresh_token or not client_id:
        db.mark_status(provider_id, "reconnect")
        raise ReconnectRequired("Sem refresh token. Autorize novamente.")
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
    if client_secret:
        data["client_secret"] = client_secret
    async with client_factory() as client:
        resp = await client.post(spec.token_url, data=data)  # type: ignore[union-attr]
    if resp.is_error:
        error = ""
        try:
            error = resp.json().get("error", "")
        except Exception:
            pass
        if error == "invalid_grant":
            db.mark_status(provider_id, "reconnect")
            db.audit("oauth.reconnect_required", provider_id)
            raise ReconnectRequired("A conexão expirou ou foi revogada. Autorize novamente.")
        log.warning("Renovação falhou (%s): HTTP %s", provider_id, resp.status_code)
        raise OAuthError("Não foi possível renovar o acesso agora.")
    body = resp.json()
    new_token = {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token") or refresh_token,
        "expires_at": time.time() + int(body.get("expires_in", 3600)),
        "token_type": body.get("token_type", "Bearer"),
    }
    db.update_token(provider_id, new_token)
    return new_token["access_token"]


async def revoke(provider_id: str) -> None:
    """Revoga no provedor (melhor esforço) e apaga o token local."""
    spec = get_provider(provider_id)
    conn = db.get_connection(provider_id)
    if spec and conn:
        tok = conn["token"].get("refresh_token") or conn["token"].get("access_token")
        try:
            async with client_factory() as client:
                await client.post(spec.revoke_url, data={"token": tok})
        except Exception as exc:  # sem internet não deve impedir a remoção local
            log.warning("Revogação remota falhou (%s): %s", provider_id, exc)
    db.delete_connection(provider_id)
    db.audit("oauth.revoked", provider_id)
