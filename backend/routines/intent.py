"""Descobre o que o usuário quer: rotina, ferramenta avulsa ou conversa comum."""
import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import llm
from .models import Routine
from .textutil import normalize
from .tools import catalog

log = logging.getLogger("jarvis.intent")


def fast_match(text: str, routines: List[Routine]) -> Optional[Routine]:
    """Caminho rápido (sem LLM): compara com os gatilhos cadastrados."""
    n = normalize(text)
    if not n:
        return None
    best, best_score = None, 0.0
    for r in routines:
        if not r.ativa:
            continue
        for g in r.gatilhos:
            gn = normalize(g)
            if not gn:
                continue
            if n == gn:
                return r
            score = SequenceMatcher(None, n, gn).ratio()
            curto = len(n.split()) <= len(gn.split()) + 3
            if curto and (n.startswith(gn + " ") or n.endswith(" " + gn)):
                score = max(score, 0.9)
            if score > best_score:
                best, best_score = r, score
    return best if best_score >= 0.85 else None


def _catalogo(routines: List[Routine], tools: List[Dict[str, Any]]) -> str:
    linhas = ["ROTINAS:"]
    for r in routines:
        if r.ativa:
            linhas.append(f"- id={r.id} | {r.nome} | {r.descricao} | exemplos: {'; '.join(r.gatilhos[:6])}")
    linhas.append("FERRAMENTAS:")
    for t in tools:
        ps = ", ".join(f"{p['nome']}({p['tipo']})" for p in t["params"] if p["nome"] != "todos_calendarios")
        linhas.append(f"- {t['nome']}: {t['descricao']}" + (f" | params: {ps}" if ps else ""))
    return "\n".join(linhas)


_SYSTEM = (
    "Você classifica pedidos falados para um assistente residencial. Decida se o pedido deve executar uma "
    "ROTINA existente, uma FERRAMENTA isolada, ou é CONVERSA comum. Responda SOMENTE com JSON: "
    '{"tipo":"rotina"|"ferramenta"|"conversa","id":"<id da rotina ou nome da ferramenta>","params":{},"confianca":0.0}\n'
    "Regras: use 'rotina' quando o pedido tem o mesmo sentido de uma rotina (mesmo com palavras diferentes). "
    "Use 'ferramenta' para consultas pontuais de dados pessoais (ex.: 'que reuniões tenho amanhã?' -> agenda.amanha; "
    "'tenho email importante?' -> gmail.para_responder). Use 'conversa' para papo, perguntas gerais, "
    "pedidos de explicação ou qualquer coisa que não dependa dos dados pessoais das fontes. "
    "Use 'ferramenta' também para pedir uma AÇÃO no computador (ex.: 'abre o profit' -> app.abrir com params "
    "{\"app\":\"profit\"}; 'organiza a tela' -> tela.organizar). "
    "Na dúvida, escolha 'conversa'. 'confianca' vai de 0 a 1."
)


async def llm_route(text: str, routines: List[Routine]) -> Optional[Dict[str, Any]]:
    tools = catalog(only_available=True)
    if not any(r.ativa for r in routines) and not tools:
        return None
    prompt = f"{_catalogo(routines, tools)}\n\nPEDIDO DO USUÁRIO: {text}"
    try:
        raw, _ = await llm.complete([{"role": "user", "content": prompt}], system=_SYSTEM,
                                    max_tokens=200, temperature=0.0, timeout=10)
        obj = llm.extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("Roteamento por LLM falhou: %s", str(exc)[:200])
        return None
    try:
        conf = float(obj.get("confianca", 0))
    except (TypeError, ValueError):
        conf = 0.0
    tipo, ident = obj.get("tipo"), obj.get("id")
    if conf < 0.6 or tipo not in ("rotina", "ferramenta"):
        return None
    if tipo == "rotina" and not any(r.id == ident and r.ativa for r in routines):
        return None
    if tipo == "ferramenta" and not any(t["nome"] == ident for t in tools):
        return None
    params = obj.get("params") if isinstance(obj.get("params"), dict) else {}
    return {"tipo": tipo, "id": ident, "params": params, "confianca": conf}
