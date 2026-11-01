"""Gmail, escrita (Fase 4): rascunhar (nível 2) e enviar (nível 3), em ferramentas SEPARADAS.

O Google não tem escopo só de rascunho: gmail.compose permite criar rascunho e também enviar. Por isso a
separação é do código: `gmail.rascunhar` só chama drafts().create (um teste confere que nenhuma chamada
de envio existe ali) e `gmail.enviar` é nível 3, só por clique seu e NUNCA dentro de tarefa (o gate recusa
mesmo que o contrato liste a ferramenta).
"""
from __future__ import annotations

import asyncio
import base64
from email.message import EmailMessage
from email.utils import getaddresses
from typing import Any, Dict, List

from ..google_auth import GoogleAuthError, check_escopo, get_service
from .registry import Param, ToolError, tool

MAX_DESTINATARIOS = 5
ASSUNTO_MAX = 200
CORPO_MAX = 20000
CORPO_MAX_ENVIO = 1500  # o cartão de confirmação mostra o texto INTEIRO; texto maior não é enviado por aqui


def _check():
    return check_escopo("gmail")


def validar(para: str, assunto: str, corpo: str, corpo_max: int = CORPO_MAX) -> Dict[str, Any]:
    """Valida antes de qualquer rede. Recusa quebra de linha em cabeçalho (injeção de cabeçalho)."""
    para = (para or "").strip()
    assunto = (assunto or "").strip()
    corpo = corpo or ""
    if any(c in para for c in "\r\n") or any(c in assunto for c in "\r\n"):
        raise ToolError("Destinatário e assunto precisam ficar em uma linha só.")
    enderecos: List[str] = [a for _, a in getaddresses([para.replace(";", ",")]) if a]
    if not enderecos or len(enderecos) > MAX_DESTINATARIOS:
        raise ToolError(f"Informe de 1 a {MAX_DESTINATARIOS} destinatários.")
    for a in enderecos:
        if a.count("@") != 1 or " " in a or not a.split("@")[1] or "." not in a.split("@")[1]:
            raise ToolError(f"Endereço inválido: {a}")
    if not assunto or len(assunto) > ASSUNTO_MAX:
        raise ToolError(f"O assunto precisa ter de 1 a {ASSUNTO_MAX} caracteres.")
    if not corpo.strip() or len(corpo) > corpo_max:
        raise ToolError(f"O corpo precisa ter de 1 a {corpo_max} caracteres.")
    return {"para": enderecos, "assunto": assunto, "corpo": corpo}


def _raw(v: Dict[str, Any]) -> str:
    m = EmailMessage()
    m["To"] = ", ".join(v["para"])
    m["Subject"] = v["assunto"]
    m.set_content(v["corpo"])
    return base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")


def _criar_rascunho(v: Dict[str, Any]) -> Dict[str, Any]:
    svc = get_service("gmail", "v1", escopo="gmail")
    r = svc.users().drafts().create(userId="me", body={"message": {"raw": _raw(v)}}).execute()
    return {"rascunho_id": r.get("id"), "link": "https://mail.google.com/mail/u/0/#drafts"}


def _enviar_email(v: Dict[str, Any]) -> Dict[str, Any]:
    svc = get_service("gmail", "v1", escopo="gmail")
    r = svc.users().messages().send(userId="me", body={"raw": _raw(v)}).execute()
    return {"mensagem_id": r.get("id")}


def _texto_rascunho(p: Dict[str, Any]) -> str:
    return f"Criar um RASCUNHO (sem enviar) para {p.get('para')}, assunto «{p.get('assunto')}»."


def _texto_envio(p: Dict[str, Any]) -> str:
    return (f"ENVIAR AGORA um e-mail para {p.get('para')}, assunto «{p.get('assunto')}». "
            f"Texto: «{p.get('corpo')}». Não dá para desfazer.")


_PARAMS = [Param("para", "str", None, "destinatário(s), separados por vírgula"),
           Param("assunto", "str", None, "assunto"),
           Param("corpo", "str", None, "texto do e-mail")]


@tool("gmail.rascunhar", "criar rascunho de e-mail",
      "Cria um RASCUNHO no Gmail. Não envia: o envio é outra ferramenta, separada e mais restrita.",
      _PARAMS, risco="externo_reversivel", timeout=30, check=_check, confirmacao=_texto_rascunho)
async def gmail_rascunhar(para=None, assunto=None, corpo=None):
    v = validar(para or "", assunto or "", corpo or "")
    try:
        r = await asyncio.to_thread(_criar_rascunho, v)
    except GoogleAuthError as exc:
        raise ToolError(str(exc)) from exc
    falado = f"Rascunho criado para {v['para'][0]}" + (" e mais destinatários." if len(v["para"]) > 1 else ".")
    return {"type": "acao", "title": "Rascunho criado", "data": {**r, "para": v["para"], "assunto": v["assunto"]},
            "falado": falado, "resumo_llm": falado}


@tool("gmail.enviar", "enviar e-mail",
      "ENVIA um e-mail agora (irreversível). Só por ação direta do usuário com confirmação; nunca em tarefa.",
      _PARAMS, risco="externo_irreversivel", timeout=30, check=_check, confirmacao=_texto_envio,
      nunca_em_tarefa=True)
async def gmail_enviar(para=None, assunto=None, corpo=None):
    v = validar(para or "", assunto or "", corpo or "", CORPO_MAX_ENVIO)
    try:
        r = await asyncio.to_thread(_enviar_email, v)
    except GoogleAuthError as exc:
        raise ToolError(str(exc)) from exc
    falado = f"E-mail enviado para {v['para'][0]}" + (" e mais destinatários." if len(v["para"]) > 1 else ".")
    return {"type": "acao", "title": "E-mail enviado", "data": {**r, "para": v["para"], "assunto": v["assunto"]},
            "falado": falado, "resumo_llm": falado}
