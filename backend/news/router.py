"""Rotas HTTP: feed na tela principal (RSS, sem chave) e pesquisa direta (útil para testar)."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import config, rss
from .intent import Intent
from .research import research

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/topics")
async def topics():
    return {"topics": rss.topic_catalog()}


@router.get("/feed")
async def feed(topic: str = Query("mercado", max_length=40), limit: int = Query(6, ge=1, le=20)):
    topic = topic.lower().strip()
    if not rss.topic_urls(topic):
        raise HTTPException(status_code=404, detail=f"Tópico desconhecido: {topic}")
    try:
        items = await rss.get_topic(topic, limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao ler feeds: {str(exc)[:200]}")
    label = config.TOPICS.get(topic, {}).get("label") or topic.title()
    return {"topic": topic, "label": label, "items": items}


class SearchRequest(BaseModel):
    query: str


@router.post("/search")
async def search(req: SearchRequest):
    q = req.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Envie uma consulta.")
    intent = Intent("search", q, q, None, "7d")
    r = await research(intent, persona="Você é JARVIS, assistente residencial. Responda em português do Brasil.")
    return {"query": r.query, "grounded": r.grounded, "answer": r.answer, "items": r.items}
