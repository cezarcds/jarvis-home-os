"""Pesquisa na web: Gemini + Google Search (usa a sua GEMINI_API_KEY atual).
Se a busca com grounding falhar (cota, erro), cai para o RSS de busca do Google Notícias
e entrega os títulos como "fatos da pesquisa" para o modelo de chat resumir."""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from . import config, rss
from .cache import TTLCache
from .enrich import enrich_many
from .intent import Intent, norm

log = logging.getLogger("jarvis.news")
_search_cache = TTLCache(ttl=config.SEARCH_TTL)

DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

NEWS_RULES = (
    "MODO NOTÍCIAS. Use a busca do Google para responder sobre fatos recentes. Regras: "
    "1) Diga somente o que as fontes encontradas sustentam; não complete lacunas com suposição. "
    "Se algo não estiver confirmado, diga que não está confirmado. "
    "2) Reescreva com suas próprias palavras; não copie trechos das matérias. "
    "3) Atribua cada afirmação ao veículo, por exemplo 'segundo a Folha' ou 'de acordo com o g1', "
    "e use mais de um veículo quando houver. "
    "4) Se os veículos divergirem em números ou versões, diga onde divergem, sem opinar nem escolher lado. "
    "5) Em política, mantenha neutralidade total, sem adjetivos de juízo. "
    "6) Situe as datas dos fatos quando isso importar. "
    "7) Resposta falada em voz alta: no máximo 5 frases curtas, sem markdown, listas, links ou emojis "
    "(esta regra prevalece sobre qualquer limite anterior de frases)."
)


@dataclass
class Research:
    query: str
    answer: Optional[str] = None       # texto pronto (grounding funcionou)
    items: list = field(default_factory=list)
    grounded: bool = False


def today_pt() -> str:
    now = datetime.now(config.TZ_BR)
    return f"{DIAS_PT[now.weekday()]}, {now:%d/%m/%Y}"


def fmt_when(iso: str | None) -> str:
    if not iso:
        return "data não informada"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(config.TZ_BR).strftime("%d/%m %H:%M")
    except ValueError:
        return "data não informada"


def facts_block(items: list[dict], header: str) -> str:
    lines = [header]
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] {it.get('outlet') or 'veículo não identificado'} ({fmt_when(it.get('published'))}): {it['title']}")
    return "\n".join(lines)


async def _gemini_grounded(query: str, persona: str) -> tuple[str, list[dict]]:
    import httpx  # import tardio

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.gemini_model()}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": f"{persona}\n\n{NEWS_RULES}"}]},
        "contents": [{"role": "user", "parts": [{"text": f"Hoje é {today_pt()}.\nPergunta do usuário: {query}"}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
    }
    headers = {"x-goog-api-key": config.gemini_key(), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        r = await client.post(url, headers=headers, json=payload)
    if r.is_error:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError("Gemini sem candidatos")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    chunks = ((cands[0].get("groundingMetadata") or {}).get("groundingChunks")) or []
    sources, seen = [], set()
    for ch in chunks:
        web = ch.get("web") or {}
        uri = web.get("uri")
        if uri and uri not in seen:
            seen.add(uri)
            sources.append({"uri": uri, "title": web.get("title", "")})
    return text, sources[:6]


async def _rss_fallback(intent: Intent) -> list[dict]:
    spec = config.TOPICS.get(intent.topic or "", {})
    query = intent.short_query
    if spec.get("query") and norm(query) in ("", norm(intent.topic or "")):
        query = spec["query"]
    return (await rss.fetch_feed(rss.google_news_search_url(query, intent.when), 10))[:6]


async def research(intent: Intent, persona: str) -> Research:
    key = norm(intent.query)
    cached = _search_cache.get(key)
    if cached:
        return cached

    result: Optional[Research] = None
    if config.gemini_key():
        t0 = time.time()
        try:
            text, sources = await _gemini_grounded(intent.query, persona)
            if text and sources:
                items = await enrich_many(sources)
                for it in items:
                    it["id"] = rss.item_id(it["url"])
                result = Research(intent.query, answer=text, items=items, grounded=True)
                log.info("Pesquisa com grounding: %d fontes em %.1fs", len(items), time.time() - t0)
            else:
                log.warning("Gemini respondeu sem fontes de grounding; usando RSS.")
        except Exception as exc:
            log.warning("Grounding falhou (%s); usando RSS.", str(exc)[:300])

    if result is None:
        try:
            items = await _rss_fallback(intent)
        except Exception as exc:
            log.warning("RSS de busca falhou: %s", str(exc)[:300])
            items = []
        result = Research(intent.query, answer=None, items=items, grounded=False)

    if result.items:  # não guardamos falhas vazias
        _search_cache.set(key, result)
    return result
