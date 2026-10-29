"""Rotas HTTP: OAuth, status das conexões e administração."""
import html
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import admin_auth, db, oauth
from .admin_auth import check_origin, require_admin
from .providers import PROVIDERS, get_provider

log = logging.getLogger("jarvis.connections")
router = APIRouter()


def _spec_or_404(provider: str):
    spec = get_provider(provider)
    if not spec:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    return spec


def _mask(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value if len(value) <= 12 else f"{value[:6]}…{value[-6:]}"


# ---- público (usado pelo HUD) ----------------------------------------------

@router.get("/connections")
async def list_connections():
    """Estado mínimo de cada provedor. Nunca devolve token nem credenciais."""
    out = []
    for spec in PROVIDERS.values():
        conn = db.get_connection_public(spec.id)
        out.append({
            "provider": spec.id,
            "label": spec.label,
            "status": conn["status"] if conn else "disconnected",
            "configured": oauth.is_configured(spec),
            # muda a cada (re)conexão: o HUD usa para saber que a autorização terminou
            "connected_at": conn["created_at"] if conn else None,
        })
    return {"connections": out}


@router.post("/auth/{provider}/start", dependencies=[Depends(check_origin)])
async def auth_start(provider: str):
    """Gera a URL de autorização. O HUD abre essa URL num popup real do navegador
    (o Google não aceita login dentro de janela embutida)."""
    _spec_or_404(provider)
    try:
        return {"authorize_url": oauth.begin(provider)}
    except oauth.NotConfigured as exc:
        raise HTTPException(status_code=400, detail={"code": "not_configured", "message": str(exc)})
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=400, detail={"code": "oauth_error", "message": str(exc)})


def _callback_page(ok: bool, provider: str, message: str) -> HTMLResponse:
    payload = json.dumps({"type": "jarvis-auth", "provider": provider, "ok": ok}).replace("<", "\\u003c")
    title = "Conectado" if ok else "Não foi possível conectar"
    body = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>JARVIS</title>
<style>body{{margin:0;height:100vh;display:grid;place-items:center;background:#02060d;color:#a5f3fc;
font-family:ui-monospace,Menlo,monospace;text-align:center}}h1{{font-weight:400;letter-spacing:.2em;font-size:1rem}}
p{{opacity:.7;font-size:.85rem}}.ok{{color:#34d399}}.err{{color:#fb7185}}</style></head><body><div>
<h1 class="{'ok' if ok else 'err'}">{html.escape(title.upper())}</h1><p>{html.escape(message)}</p></div>
<script>try{{window.opener&&window.opener.postMessage({payload},"*")}}catch(e){{}}
setTimeout(function(){{window.close()}},{1200 if ok else 4000});</script></body></html>"""
    return HTMLResponse(
        body,
        status_code=200 if ok else 400,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/auth/{provider}/callback")
async def auth_callback(
    provider: str,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    if not get_provider(provider):
        return _callback_page(False, provider, "Provedor desconhecido.")
    if error:
        db.audit("oauth.denied", f"{provider} {error[:60]}")
        return _callback_page(False, provider, "Autorização cancelada. Você pode fechar esta janela.")
    if not code or not state:
        return _callback_page(False, provider, "Resposta incompleta do provedor.")
    try:
        account = await oauth.finish(provider, code, state)
    except oauth.OAuthError as exc:
        return _callback_page(False, provider, str(exc))
    except Exception:
        log.exception("Erro inesperado no callback de %s", provider)
        return _callback_page(False, provider, "Erro interno ao concluir a conexão.")
    return _callback_page(True, provider, f"Conta {account} conectada. Esta janela vai fechar.")


# ---- admin ------------------------------------------------------------------

class PasswordBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class CredentialsBody(BaseModel):
    client_id: str = Field(min_length=5, max_length=300)
    client_secret: Optional[str] = Field(default=None, max_length=300)


class ScopesBody(BaseModel):
    scopes: list[str] = Field(default_factory=list, max_length=20)


@router.get("/admin/status", dependencies=[Depends(check_origin)])
async def admin_status(request: Request):
    return {
        "password_set": admin_auth.is_password_set(),
        "authenticated": admin_auth.validate_session(request.headers.get("x-jarvis-admin")),
    }


@router.post("/admin/setup", dependencies=[Depends(check_origin)])
async def admin_setup(body: PasswordBody):
    if admin_auth.is_password_set():
        raise HTTPException(status_code=409, detail="A senha já foi definida.")
    try:
        admin_auth.set_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"token": admin_auth.create_session()}


@router.post("/admin/login", dependencies=[Depends(check_origin)])
async def admin_login(body: PasswordBody):
    if not admin_auth.is_password_set():
        raise HTTPException(status_code=409, detail="Defina a senha primeiro.")
    try:
        ok = admin_auth.verify_password(body.password)
    except admin_auth.Locked as exc:
        raise HTTPException(status_code=429, detail=f"Muitas tentativas. Aguarde {exc.seconds}s.")
    if not ok:
        raise HTTPException(status_code=401, detail="Senha incorreta.")
    return {"token": admin_auth.create_session()}


@router.post("/admin/logout", dependencies=[Depends(check_origin)])
async def admin_logout(request: Request):
    admin_auth.end_session(request.headers.get("x-jarvis-admin"))
    return {"ok": True}


@router.get("/admin/overview")
async def admin_overview(_: str = Depends(require_admin)):
    providers = []
    for spec in PROVIDERS.values():
        cid, _secret, source = oauth.get_credentials(spec)
        conn = db.get_connection_public(spec.id)
        enabled = set(oauth.enabled_scopes(spec))
        providers.append({
            "id": spec.id,
            "label": spec.label,
            "configured": cid is not None,
            "credentials_source": source,
            "client_id_masked": _mask(cid),
            "redirect_uri": oauth.redirect_uri(spec),
            "status": conn["status"] if conn else "disconnected",
            "account": conn["account"] if conn else None,
            "granted_scopes": conn["scopes"] if conn else [],
            "connected_at": conn["created_at"] if conn else None,
            "last_sync": conn["last_sync"] if conn else None,
            "base_scopes": list(spec.base_scopes),
            "optional_scopes": [
                {"scope": s, "label": label, "enabled": s in enabled}
                for s, label in spec.optional_scopes.items()
            ],
        })
    return {"providers": providers, "audit": db.recent_audit(20)}


@router.put("/admin/providers/{provider}/credentials")
async def admin_set_credentials(provider: str, body: CredentialsBody, _: str = Depends(require_admin)):
    spec = _spec_or_404(provider)
    db.set_setting(f"oauth.{spec.id}.client_id", body.client_id.strip())
    if body.client_secret and body.client_secret.strip():
        db.set_setting(f"oauth.{spec.id}.client_secret", body.client_secret.strip())
    else:
        db.delete_setting(f"oauth.{spec.id}.client_secret")
    db.audit("admin.credentials_set", spec.id)
    return {"ok": True}


@router.put("/admin/providers/{provider}/scopes")
async def admin_set_scopes(provider: str, body: ScopesBody, _: str = Depends(require_admin)):
    spec = _spec_or_404(provider)
    invalid = [s for s in body.scopes if s not in spec.optional_scopes]
    if invalid:
        raise HTTPException(status_code=400, detail="Escopo não permitido para este provedor.")
    db.set_setting(f"scopes.{spec.id}", json.dumps(body.scopes))
    db.audit("admin.scopes_set", f"{spec.id} {len(body.scopes)} extras")
    return {"ok": True, "note": "Reconecte a conta para aplicar os novos escopos."}


@router.post("/connections/{provider}/revoke")
async def revoke_connection(provider: str, _: str = Depends(require_admin)):
    _spec_or_404(provider)
    await oauth.revoke(provider)
    return {"ok": True}
