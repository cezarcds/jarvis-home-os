"""Gmail (somente leitura)."""
import asyncio
import html
import re
from datetime import datetime
from email.utils import parseaddr
from typing import Any, Dict, List

from ..google_auth import check_google, get_service
from .registry import Param, ToolError, tool
from .util import TZ, plural

_NOREPLY = re.compile(r"(no[-_.]?reply|do[-_.]?not[-_.]?reply|notifications?@|mailer-daemon|newsletter)", re.I)
_HEADERS = ["From", "Subject", "Date", "List-Unsubscribe"]
_me_cache: Dict[str, str] = {}


def _meu_email(svc) -> str:
    if "me" not in _me_cache:
        _me_cache["me"] = svc.users().getProfile(userId="me").execute().get("emailAddress", "").lower()
    return _me_cache["me"]


def _threads(svc, ids: List[str]) -> List[Dict[str, Any]]:
    """Busca metadados de várias threads em uma única requisição em lote."""
    if not ids:
        return []
    out: Dict[str, Any] = {}

    def cb(request_id, response, exception):
        if exception is None:
            out[request_id] = response

    batch = svc.new_batch_http_request(callback=cb)
    for tid in ids:
        batch.add(
            svc.users().threads().get(userId="me", id=tid, format="metadata", metadataHeaders=_HEADERS),
            request_id=tid,
        )
    batch.execute()
    return [out[i] for i in ids if i in out]


def _item(th: Dict[str, Any]) -> Dict[str, Any]:
    last = th["messages"][-1]
    hdr = {h["name"].lower(): h["value"] for h in last.get("payload", {}).get("headers", [])}
    nome, addr = parseaddr(hdr.get("from", ""))
    ts = datetime.fromtimestamp(int(last.get("internalDate", "0")) / 1000, TZ)
    return {
        "id": th["id"],
        "de": nome or addr or "(desconhecido)",
        "endereco": addr.lower(),
        "assunto": hdr.get("subject") or "(sem assunto)",
        "trecho": html.unescape(last.get("snippet", ""))[:160],
        "data": ts.isoformat(),
        "nao_lido": "UNREAD" in last.get("labelIds", []),
        "newsletter": "list-unsubscribe" in hdr,
        "enviado_por_mim": "SENT" in last.get("labelIds", []),
        "link": f"https://mail.google.com/mail/u/0/#inbox/{th['id']}",
    }


def _para_responder(dias: int, max_itens: int, so_importantes: bool) -> Dict[str, Any]:
    svc = get_service("gmail", "v1")
    me = _meu_email(svc)
    q = f"in:inbox -category:promotions -category:social -category:forums newer_than:{dias}d"
    if so_importantes:
        q += " is:important"
    ids = [t["id"] for t in svc.users().threads().list(userId="me", q=q, maxResults=min(max_itens * 5, 40))
           .execute().get("threads", [])]
    itens = []
    for th in _threads(svc, ids):
        it = _item(th)
        if it["endereco"] == me or it["enviado_por_mim"] or it["newsletter"] or _NOREPLY.search(it["endereco"]):
            continue
        itens.append(it)
    itens.sort(key=lambda x: x["data"], reverse=True)
    return {"itens": itens[:max_itens], "candidatos": len(itens)}


def _nao_lidos(max_itens: int) -> Dict[str, Any]:
    svc = get_service("gmail", "v1")
    total = svc.users().labels().get(userId="me", id="INBOX").execute().get("messagesUnread", 0)
    q = "in:inbox is:unread -category:promotions -category:social -category:forums"
    ids = [t["id"] for t in svc.users().threads().list(userId="me", q=q, maxResults=max_itens).execute().get("threads", [])]
    itens = sorted((_item(t) for t in _threads(svc, ids)), key=lambda x: x["data"], reverse=True)
    return {"itens": itens[:max_itens], "total_nao_lidos": total}


def _resumo_llm(itens) -> str:
    # Só remetente e assunto vão para o LLM (sem corpo/trecho dos emails).
    return "\n".join(f"de: {i['de']} | assunto: {i['assunto']}" for i in itens) or "(nenhum)"


@tool(
    "gmail.para_responder", "emails para responder",
    "Emails recentes da caixa de entrada cuja última mensagem é de outra pessoa (exclui promoções, "
    "newsletters e avisos automáticos)",
    [Param("max", "int", 5, "Máximo de emails", 1, 15),
     Param("dias", "int", 7, "Janela em dias", 1, 30),
     Param("so_importantes", "bool", False, "Só emails marcados como importantes pelo Gmail")],
    check=check_google,
)
async def gmail_para_responder(max=5, dias=7, so_importantes=False):
    data = await asyncio.to_thread(_para_responder, int(dias), int(max), bool(so_importantes))
    itens = data["itens"]
    n = len(itens)
    if n == 0:
        falado = "Nenhum email aguardando resposta."
    else:
        falado = (f"Há {n} {plural(n, 'email aguardando', 'emails aguardando')} resposta. "
                  f"O mais recente é de {itens[0]['de']}, sobre {itens[0]['assunto']}.")
    return {"type": "emails", "title": "Emails para responder", "data": data,
            "falado": falado, "resumo_llm": _resumo_llm(itens)}


@tool(
    "gmail.nao_lidos", "emails não lidos",
    "Quantidade de emails não lidos na caixa de entrada e os mais recentes (sem promoções)",
    [Param("max", "int", 5, "Máximo de emails listados", 1, 15)],
    check=check_google,
)
async def gmail_nao_lidos(max=5):
    data = await asyncio.to_thread(_nao_lidos, int(max))
    total = data["total_nao_lidos"]
    falado = f"Você tem {total} {plural(total, 'email não lido', 'emails não lidos')}."
    return {"type": "emails", "title": "Emails não lidos", "data": data,
            "falado": falado, "resumo_llm": f"total não lidos: {total}\n" + _resumo_llm(data["itens"])}
