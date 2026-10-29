"""Rotas HTTP: assistente (voz/texto), CRUD de rotinas e catálogo de ferramentas."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

import llm
from . import creator, engine, intent, store
from .models import Routine
from .textutil import normalize
from .tools import ToolError, catalog
from .tools.util import DIAS, TZ

log = logging.getLogger("jarvis.api")
router = APIRouter(prefix="/v1")

SYSTEM_BASE = (
    "Você é JARVIS, um assistente residencial sofisticado, calmo e levemente irônico. Responda sempre em português "
    "do Brasil, de forma concisa, com 1 a 4 frases, pois suas respostas serão faladas em voz alta. "
    "Não use markdown, listas nem emojis. Priorize respostas diretas e naturais."
)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class AssistantRequest(BaseModel):
    messages: List[ChatMessage]
    session_id: str = "default"


def _system_chat() -> str:
    agora = datetime.now(TZ)
    rotinas = [r for r in store.list_routines() if r.ativa]
    nomes = "; ".join(f"{r.nome} (diga '{r.gatilhos[0]}')" if r.gatilhos else r.nome for r in rotinas)
    return (
        f"{SYSTEM_BASE}\nAgora: {DIAS[agora.weekday()]}, {agora.strftime('%d/%m/%Y %H:%M')}.\n"
        f"Rotinas que você sabe executar: {nomes or 'nenhuma'}. "
        "Nesta conversa comum você NÃO tem acesso a emails, agenda, Analytics ou redes sociais; esses dados só chegam "
        "quando uma rotina ou consulta é acionada. Se o usuário pedir algo assim e não foi acionado, diga isso com "
        "naturalidade e sugira criar uma rotina (ex.: 'crie uma rotina chamada ...'). Nunca invente dados pessoais."
    )


def _resposta_rotina(res: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "rotina",
        "text": res["fala"],
        "scene": {"titulo": res["titulo"], "blocos": res["blocos"], "rotina": res["rotina"]},
    }


def _resposta_bloco(texto: str, bloco: Dict[str, Any], titulo: str, kind: str) -> Dict[str, Any]:
    return {"kind": kind, "text": texto, "scene": {"titulo": titulo, "blocos": [bloco] if bloco else [], "rotina": None}}


def _bloco_lista() -> Dict[str, Any]:
    rotinas = store.list_routines()
    return {"type": "rotinas", "title": "Suas rotinas", "data": {"itens": [
        {"id": r.id, "nome": r.nome, "ativa": r.ativa, "gatilhos": r.gatilhos[:3],
         "fontes": [s.ferramenta for s in r.passos]} for r in rotinas]}}


@router.post("/assistant")
async def assistant(req: AssistantRequest):
    users = [m for m in req.messages if m.role == "user"]
    if not users:
        raise HTTPException(400, "Envie pelo menos uma mensagem do usuário.")
    text = users[-1].content.strip()
    sid = req.session_id
    history = [m.model_dump() for m in req.messages if m.role != "system"][-12:]

    # 1) Rascunho de rotina aguardando confirmação
    pending = creator.get_pending(sid)
    if pending:
        if creator.eh_confirmacao(text):
            txt, bloco = creator.confirmar(sid)
            return {**_resposta_bloco(txt, bloco, "Rotinas", "rotina_salva"), "provider": None}
        if creator.eh_cancelamento(text):
            creator.clear_pending(sid)
            return {"kind": "cancelado", "text": "Certo, cancelei.", "scene": None, "provider": None}
        if creator.eh_refinamento(text):
            base = {"acao": pending["acao"], "alvo": pending["alvo_id"], "rotina": pending["rotina"]}
            txt, bloco = await creator.rascunhar(sid, text, base=base)
            return {**_resposta_bloco(txt, bloco, "Confirme a rotina", "rascunho"), "provider": None}
        creator.clear_pending(sid)  # assunto novo: descarta o rascunho

    # 2) Criar/editar/apagar rotina por voz
    if creator.eh_comando_de_rotina(text):
        txt, bloco = await creator.rascunhar(sid, text)
        return {**_resposta_bloco(txt, bloco, "Confirme a rotina", "rascunho"), "provider": None}

    # 3) Listar rotinas
    if creator.eh_listagem(text):
        rs = [r for r in store.list_routines() if r.ativa]
        txt = ("Você tem " + str(len(rs)) + " rotinas ativas: " + ", ".join(r.nome for r in rs) + "."
               if rs else "Você ainda não tem rotinas.")
        return {**_resposta_bloco(txt, _bloco_lista(), "Suas rotinas", "lista"), "provider": None}

    # 4) Rotina por gatilho (caminho rápido) ou por significado (LLM)
    rotinas = store.list_routines()
    alvo = intent.fast_match(text, rotinas)
    if alvo:
        log.info("Rotina '%s' (gatilho direto)", alvo.id)
        return {**_resposta_rotina(await engine.run_routine(alvo)), "provider": None}

    decisao = await intent.llm_route(text, rotinas)
    if decisao:
        log.info("Roteamento LLM: %s", decisao)
        if decisao["tipo"] == "rotina":
            r = next(x for x in rotinas if x.id == decisao["id"])
        else:
            try:
                r = engine.rotina_avulsa(decisao["id"], decisao["params"])
            except ValidationError:
                r = None
        if r:
            return {**_resposta_rotina(await engine.run_routine(r)), "provider": None}

    # 5) Conversa comum
    try:
        reply, provider = await llm.complete(history, system=_system_chat(), max_tokens=400, temperature=0.7)
    except llm.LLMError as exc:
        raise HTTPException(502, detail={"message": "Nenhum provedor de IA respondeu.", "errors": [str(exc)]})
    return {"kind": "chat", "text": reply, "scene": None, "provider": provider}


# ---------- CRUD de rotinas e catálogo ----------

@router.get("/tools")
async def list_tools():
    return catalog()


@router.get("/routines")
async def list_routines():
    return [r.model_dump() for r in store.list_routines()]


def _validar_salvar(r: Routine) -> Routine:
    from .tools import REGISTRY, coerce_params
    for s in r.passos:
        t = REGISTRY.get(s.ferramenta)
        if not t:
            raise HTTPException(422, f"Ferramenta inexistente: {s.ferramenta}")
        try:
            coerce_params(t, s.params)
        except ToolError as exc:
            raise HTTPException(422, str(exc))
    if r.tipo != "leitura":
        raise HTTPException(422, "Rotinas de ação ainda não são suportadas.")
    return r


@router.post("/routines")
async def create_routine(r: Routine):
    r.id = ""
    return store.upsert(_validar_salvar(r)).model_dump()


@router.put("/routines/{routine_id}")
async def update_routine(routine_id: str, r: Routine):
    if not store.get(routine_id):
        raise HTTPException(404, "Rotina não encontrada.")
    r.id = routine_id
    return store.upsert(_validar_salvar(r)).model_dump()


@router.delete("/routines/{routine_id}")
async def delete_routine(routine_id: str):
    if not store.delete(routine_id):
        raise HTTPException(404, "Rotina não encontrada.")
    return {"ok": True}


@router.post("/routines/{routine_id}/run")
async def run_routine(routine_id: str):
    r = store.get(routine_id)
    if not r:
        raise HTTPException(404, "Rotina não encontrada.")
    try:
        return _resposta_rotina(await engine.run_routine(r))
    except ToolError as exc:
        raise HTTPException(422, str(exc))
