"""Rotas das tarefas (/v1/tarefas). Passam pelo guarda da Fase 0 (token + Host + Origin).

Criação é por JSON (Fase 5 traz a criação por conversa). Quem tem o token pode criar tarefa e marcar o
contrato como aprovado: o contrato é a SUA autoridade; nada aqui é chamado por LLM ou por conteúdo
externo, e a criação por conversa (Fase 5) terá de passar por uma aprovação explícita na tela.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ValidationError

from . import executor, pasta, store
from .agendador import Agendador
from .models import SchemaNaoSuportado, carregar

log = logging.getLogger("jarvis.tarefas")
router = APIRouter(prefix="/v1/tarefas")

_em_segundo_plano: set = set()  # referências às execuções manuais (senão o asyncio pode coletá-las)


def _agendador(request: Request) -> Agendador:
    ag = getattr(request.app.state, "agendador", None)
    if ag is None:
        ag = request.app.state.agendador = Agendador()
    return ag


def _resumo(t) -> Dict[str, Any]:
    ultima = store.execucoes(t.id, 1)
    return {"id": t.id, "nome": t.nome, "ativa": t.ativa, "agenda": t.agenda.model_dump() if t.agenda else None,
            "contrato_aprovado": t.contrato.aprovado, "passos": [p.id for p in t.passos],
            "ultima_execucao": ultima[0] if ultima else None}


def _tarefa_ou_404(id_: str):
    t = store.obter(id_)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    return t


# ---- estado e agendador (antes das rotas com {id}) -------------------------------------------------------

@router.get("/estado")
async def estado(request: Request) -> Dict[str, Any]:
    return _agendador(request).estado()


@router.post("/agendador/pausar")
async def pausar(request: Request) -> Dict[str, Any]:
    _agendador(request).pausar("hud")
    return {"pausado": True}


@router.post("/agendador/retomar")
async def retomar(request: Request) -> Dict[str, Any]:
    _agendador(request).retomar()
    return {"pausado": False}


@router.post("/importar")
async def importar() -> Dict[str, Any]:
    """Lê os .json de ~/.jarvis/tarefas/ (escritos à mão)."""
    return {"pasta": str(pasta.pasta()), "resultados": pasta.importar()}


@router.get("/execucoes/{execucao_id}")
async def execucao(execucao_id: str) -> Dict[str, Any]:
    e = store.obter_execucao(execucao_id)
    if not e:
        raise HTTPException(404, "Execução não encontrada.")
    return e


# ---- tarefas ---------------------------------------------------------------------------------------------------

@router.get("")
async def listar() -> Dict[str, Any]:
    return {"tarefas": [_resumo(t) for t in store.listar()]}


@router.post("")
async def salvar(body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        t = carregar(body)
    except SchemaNaoSuportado as exc:
        raise HTTPException(422, str(exc))
    except ValidationError as exc:
        raise HTTPException(422, "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())[:800])
    store.salvar(t)
    return _resumo(t)


@router.get("/{tarefa_id}")
async def obter(tarefa_id: str) -> Dict[str, Any]:
    t = _tarefa_ou_404(tarefa_id)
    return {**_resumo(t), "tarefa": t.dump(), "itens": store.itens_da_tarefa(tarefa_id)}


@router.delete("/{tarefa_id}")
async def remover(tarefa_id: str) -> Dict[str, Any]:
    if not store.remover(tarefa_id):
        raise HTTPException(404, "Tarefa não encontrada.")
    return {"ok": True}


class AtivaBody(BaseModel):
    ativa: bool


@router.put("/{tarefa_id}/ativa")
async def ativar(tarefa_id: str, body: AtivaBody) -> Dict[str, Any]:
    if not store.definir_ativa(tarefa_id, body.ativa):
        raise HTTPException(404, "Tarefa não encontrada.")
    return {"ativa": body.ativa}


@router.get("/{tarefa_id}/execucoes")
async def execucoes(tarefa_id: str, limite: int = 30) -> Dict[str, Any]:
    _tarefa_ou_404(tarefa_id)
    return {"execucoes": store.execucoes(tarefa_id, max(1, min(limite, 200)))}


@router.post("/{tarefa_id}/simular")
async def simular(tarefa_id: str) -> Dict[str, Any]:
    """Dry-run: o que cada passo faria e se o contrato deixaria. Não executa nada."""
    return executor.simular(_tarefa_ou_404(tarefa_id))


@router.post("/{tarefa_id}/executar")
async def executar(tarefa_id: str) -> Dict[str, Any]:
    """Roda agora, em segundo plano. Devolve a execução criada; acompanhe em /execucoes/{id}."""
    t = _tarefa_ou_404(tarefa_id)
    antes = {e["id"] for e in store.execucoes(tarefa_id, 20)}
    saida: Dict[str, Any] = {}

    async def _rodar() -> None:
        try:
            saida["r"] = await executor.executar_tarefa(t)
        except Exception:  # noqa: BLE001
            log.exception("Execução manual de %s falhou", tarefa_id)

    task = asyncio.ensure_future(_rodar())
    _em_segundo_plano.add(task)
    task.add_done_callback(_em_segundo_plano.discard)
    for _ in range(40):  # a linha da execução nasce logo no começo de executar_tarefa
        await asyncio.sleep(0.05)
        nova = next((e for e in store.execucoes(tarefa_id, 20) if e["id"] not in antes), None)
        if nova:
            return {"iniciada": True, "execucao": nova}
        if task.done():
            break
    r = saida.get("r")
    if r is not None and r.estado in ("ja_em_execucao", "ja_executada"):
        raise HTTPException(409, r.motivo)
    return {"iniciada": not task.done(), "execucao": None}


@router.delete("/{tarefa_id}/itens")
async def liberar_item(tarefa_id: str, chave: str) -> Dict[str, Any]:
    """Libera um item 'incerto' depois de você conferir que NÃO foi enviado."""
    _tarefa_ou_404(tarefa_id)
    if not chave.startswith(f"{tarefa_id}:"):
        raise HTTPException(422, "Chave de outra tarefa.")
    if not store.item_liberar(chave):
        raise HTTPException(404, "Item não encontrado.")
    return {"ok": True}
