"""Rotas do gate: listar, confirmar e negar ações pendentes, e o botão de parada.

Todas passam pelo guarda da Fase 0 (token de sessão + Host + Origin). Importante: quem tem o
token consegue chamar /confirmar; o "clique" é a via declarada, não uma prova de que foi uma
pessoa. A proteção real contra um site mal-intencionado é o token somado à checagem de Origin.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from . import gate, handler

log = logging.getLogger("jarvis.gate")
router = APIRouter(prefix="/v1/gate")


@router.get("/pendentes")
async def pendentes() -> Dict[str, Any]:
    return {"pendentes": gate.listar_pendentes()}


@router.post("/parar")
async def parar() -> Dict[str, Any]:
    return {"ok": True, **gate.parar("hud")}


@router.post("/{pendente_id}/confirmar")
async def confirmar(pendente_id: str) -> Dict[str, Any]:
    try:
        res = await gate.confirmar(pendente_id, "clique")
    except gate.ConfirmacaoInvalida as exc:
        raise HTTPException(409, str(exc))
    except gate.ExecucaoCancelada as exc:
        raise HTTPException(409, str(exc))
    except (gate.AcaoNegada, gate.ToolError) as exc:
        raise HTTPException(422, str(exc))
    except Exception:  # noqa: BLE001
        log.exception("Falha ao executar a ação confirmada")
        raise HTTPException(500, "Algo deu errado ao executar a ação. Os detalhes estão no log do backend.")
    return handler.resposta_do_resultado(res)


@router.post("/{pendente_id}/negar")
async def negar(pendente_id: str) -> Dict[str, Any]:
    try:
        gate.negar(pendente_id)
    except gate.ConfirmacaoInvalida as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}
