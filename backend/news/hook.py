"""Ponto de encaixe com o chat do Jarvis (3 chamadas no main.py)."""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from . import config, rss
from .intent import detect
from .research import facts_block, research

log = logging.getLogger("jarvis.news")

RULES_FOR_CHAT = (
    "Use apenas estes fatos; não invente nada além deles. Reescreva com suas próprias palavras. "
    "Atribua cada afirmação ao veículo ('segundo a Folha'). Se os veículos divergirem, aponte onde, "
    "sem opinar. Resposta falada, no máximo 5 frases curtas, sem markdown."
)


@dataclass
class NewsContext:
    kind: str
    query: str
    topic: Optional[str]
    items: list = field(default_factory=list)
    answer: Optional[str] = None
    facts: str = ""
    grounded: bool = False

    def payload(self) -> dict:
        """Contrato com o frontend. Cada item: id, title, outlet, url, published (ISO UTC), image."""
        return {
            "kind": self.kind,
            "query": self.query,
            "topic": self.topic,
            "grounded": self.grounded,
            "generated_at": int(time.time()),
            "items": self.items,
        }

    def completion(self) -> dict:
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": config.gemini_model(),
            "provider": "gemini-search",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": self.answer}, "finish_reason": "stop"}],
        }


async def _briefing_items() -> list[dict]:
    out: list[dict] = []
    for topic in config.BRIEFING_TOPICS:
        try:
            items = await rss.get_topic(topic, config.BRIEFING_PER_TOPIC)
        except Exception as exc:
            log.warning("Briefing: tópico %s falhou: %s", topic, str(exc)[:200])
            continue
        for it in items:
            out.append({**it, "topic": topic})
    return out


async def _prepare(user_text: str, persona: str) -> Optional[NewsContext]:
    intent = detect(user_text)
    if not intent:
        return None
    log.info("Intenção de notícias detectada: %s | %s", intent.kind, user_text[:80])

    if intent.kind == "briefing":
        items = await _briefing_items()
        ctx = NewsContext("briefing", "bom dia", None, items)
        header = "FATOS DA PESQUISA (manchetes de hoje; mercado primeiro). Faça um bom dia curto e resuma as principais."
    else:
        r = await research(intent, persona)
        ctx = NewsContext("search", intent.query, intent.topic, r.items, r.answer, grounded=r.grounded)
        if r.answer:
            return ctx
        header = "FATOS DA PESQUISA (títulos recentes encontrados)."

    if ctx.items:
        ctx.facts = facts_block(ctx.items, header) + "\n" + RULES_FOR_CHAT
    else:
        ctx.facts = (
            "FATOS DA PESQUISA: nenhuma fonte foi obtida agora. Diga ao usuário que não conseguiu buscar "
            "notícias neste momento e NÃO invente fatos."
        )
    return ctx


async def prepare_news(messages: list[dict], persona: str = "") -> Optional[NewsContext]:
    """Nunca levanta exceção: se algo falhar, o Jarvis segue como chat normal."""
    if not config.enabled():
        return None
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    try:
        return await asyncio.wait_for(_prepare(last_user, persona), timeout=config.SEARCH_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("Pesquisa de notícias estourou o tempo; seguindo como chat normal.")
    except Exception:
        log.exception("Falha no módulo de notícias; seguindo como chat normal.")
    return None


def inject_facts(messages: list[dict], ctx: NewsContext) -> list[dict]:
    """Coloca os fatos junto da última fala do usuário (funciona para Groq e Gemini)."""
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user":
            m["content"] = f"{ctx.facts}\n\nPergunta do usuário: {m['content']}"
            break
    return out


def attach_news(result: dict, ctx: Optional[NewsContext]) -> dict:
    if ctx and ctx.items:
        result["news"] = ctx.payload()
    return result
