"""Rotas de diagnóstico: ver o catálogo de programas e as janelas abertas (útil para ajustar o apps.json)."""
import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from . import apps, handler
from .config import actions_enabled, jarvis_window_regex

router = APIRouter(prefix="/v1/actions")


@router.get("/apps")
async def list_apps() -> List[Dict[str, Any]]:
    return [
        {"id": e.id, "nomes": e.nomes, "titulo_regex": e.titulo_regex, "processos": e.processos,
         "atalho": e.atalho, "layout": e.layout}
        for e in apps.load_catalog()
    ]


@router.get("/windows")
async def list_windows() -> List[Dict[str, Any]]:
    """Janelas abertas agora, com o nome do executável: é o que se coloca em 'processos' e 'titulo_regex'."""
    if not handler.win.AVAILABLE:
        raise HTTPException(501, "Disponível só no Windows.")
    if not actions_enabled():
        raise HTTPException(403, "Ações desligadas (JARVIS_ACTIONS_ENABLED=0).")
    rx = jarvis_window_regex()
    wins = await asyncio.to_thread(handler.win.list_windows)
    return [{"titulo": w.title, "processo": w.process, "minimizada": w.minimized,
             "jarvis": bool(rx.search(w.title)),
             "retangulo": [w.rect.left, w.rect.top, w.rect.right, w.rect.bottom]} for w in wins]
