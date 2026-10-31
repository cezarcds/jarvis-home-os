"""Notícias dentro do motor de cenas: a pesquisa vira uma cena do palco.

A fala do Jarvis (a resposta pesquisada, atribuída aos veículos) é dividida em trechos; cada trecho mostra um
mural de cartões de notícia (capa, veículo, hora, manchete) e uma chamada lateral com o veículo citado.
O mesmo formato de /v1/scene, então o palco, o mural e as chamadas que você já tem desenham tudo.

Duas entradas usam isto: POST /v1/scene (perguntas faladas como "o que aconteceu hoje com o dólar?") e
POST /v1/assistant (pedidos como "últimas notícias do mercado" que o app manda para o assistente).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from scene_schema import sanitize_scene

from . import config
from .hook import NewsContext, inject_facts, prepare_news
from .intent import _short_query, norm

log = logging.getLogger("jarvis.news")

MAX_BEATS = 6        # trechos de fala por cena
MAX_CARDS = 6        # cartões de notícia por cena (o palco mostra até 3 ao mesmo tempo aqui)
SHOW = 3             # cartões visíveis por trecho
SAY_MAX = 230        # tamanho máximo de um trecho falado (o esquema aceita até 260)
LLM_TIMEOUT = 18.0

# Veículos cujo primeiro nome é uma palavra comum: só contam como citados se o nome inteiro aparecer.
_AMBIGUOUS = {"valor", "agencia", "correio", "terra", "exame"}
_OUTLET_STOP = {"de", "do", "da", "o", "a", "s", "e", "dos", "das"}


def clean_spoken(text: str) -> str:
    """Tira o que não se fala: marcadores [1], links, markdown e listas."""
    t = text or ""
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", t)
    t = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", "", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*_`#>]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()


def _hard_split(sentence: str, limit: int) -> list[str]:
    """Frase maior que o limite: corta na última vírgula, ponto e vírgula ou espaço antes dele."""
    out = []
    rest = sentence.strip()
    while len(rest) > limit:
        cut = max(rest.rfind(", ", 0, limit), rest.rfind("; ", 0, limit))
        if cut < limit * 0.4:
            cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        out.append(rest[: cut + 1].strip())
        rest = rest[cut + 1 :].strip()
    if rest:
        out.append(rest)
    return out


def split_beats(text: str, limit: int = SAY_MAX, max_beats: int = MAX_BEATS) -> list[str]:
    """Agrupa as frases em trechos falados de até `limit` letras (uma ou duas frases cada)."""
    sentences: list[str] = []
    for s in re.split(r"(?<=[.!?…])\s+", text.strip()):
        sentences.extend(_hard_split(s, limit) if len(s) > limit else [s])
    beats: list[str] = []
    cur = ""
    for s in (x for x in sentences if x):
        if cur and len(cur) + 1 + len(s) > limit:
            beats.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        beats.append(cur)
    return beats[:max_beats]


def outlet_mentioned(outlet: str, spoken: str) -> bool:
    """O veículo é citado na fala? ('segundo a Folha' cita 'Folha de S.Paulo')."""
    tokens = [w for w in re.findall(r"[a-z0-9]+", norm(outlet)) if w not in _OUTLET_STOP]
    if not tokens:
        return False
    words = set(re.findall(r"[a-z0-9]+", norm(spoken)))
    if tokens[0] in _AMBIGUOUS:
        return all(t in words for t in tokens)
    return tokens[0] in words


def _hora(iso: Optional[str]) -> str:
    """Hoje: 'HH:MM'. Outro dia: 'dd/mm'. Sem data: vazio."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(config.TZ_BR)
    today = datetime.now(config.TZ_BR).date()
    return local.strftime("%H:%M") if local.date() == today else local.strftime("%d/%m")


def pick_items(items: list[dict]) -> list[dict]:
    """Até MAX_CARDS fontes sem repetir, com as que têm capa primeiro (mantendo a ordem entre elas)."""
    seen, uniq = set(), []
    for it in items or []:
        key = it.get("url") or it.get("id")
        url = str(it.get("url") or "")
        if not key or key in seen or not it.get("title") or not url.lower().startswith(("http://", "https://")):
            continue
        seen.add(key)
        uniq.append(it)
    uniq.sort(key=lambda it: 0 if it.get("image") else 1)  # sort é estável
    return uniq[:MAX_CARDS]


def scene_title(ctx: NewsContext) -> str:
    if ctx.kind == "briefing":
        return "Resumo do dia"
    short = _short_query(ctx.query or "")
    if short and len(short) <= 40:
        return f"Notícias: {short}"
    label = config.TOPICS.get(ctx.topic or "", {}).get("label")
    return f"Notícias: {label}" if label else "Notícias"


def _callout(it: dict, mid: str, side: str, at: float) -> Optional[dict]:
    outlet = (it.get("outlet") or "").strip()
    if not outlet:
        return None
    hora = _hora(it.get("published"))
    return {"text": f"{outlet} · {hora}" if hora else outlet, "side": side, "at": at, "kind": "term", "target": mid}


def build_scene(text: str, ctx: NewsContext, provider: str = "gemini-search") -> dict:
    """Cena no formato do /v1/scene. Levanta ValueError se não houver o que falar."""
    items = pick_items(ctx.items)
    media = [
        {
            "id": f"n{i + 1}", "kind": "news", "query": it["title"][:80], "caption": "",
            "news": {k: it.get(k) for k in ("title", "outlet", "url", "image", "published")},
        }
        for i, it in enumerate(items)
    ]
    by_id = {m["id"]: it for m, it in zip(media, items)}

    beats = []
    for i, say in enumerate(split_beats(text)):
        if not media:
            beats.append({"say": say, "layout": "title", "caption": "", "keyword": ""})
            continue
        n = min(SHOW, len(media))
        start = (i * 2) % len(media)
        window = [media[(start + k) % len(media)]["id"] for k in range(n)]
        cited = [m["id"] for m in media if outlet_mentioned(by_id[m["id"]].get("outlet") or "", say)]
        featured = cited[0] if cited else window[0]
        show = [featured] + [w for w in window if w != featured][: n - 1]
        callouts = []
        for k, mid in enumerate(([featured] + [c for c in cited if c != featured])[:2]):
            c = _callout(by_id[mid], mid, "left" if k == 0 else "right", 0.15 if k == 0 else 0.55)
            if c:
                callouts.append(c)
        beats.append({
            "say": say, "layout": "media", "media": featured, "show": show,
            "caption": "", "reveal": [], "focus": [], "callouts": callouts,
        })

    scene = sanitize_scene({"title": scene_title(ctx), "topic_kind": "news", "media": media, "beats": beats})
    scene["id"] = uuid.uuid4().hex[:10]
    scene["answer"] = " ".join(b["say"] for b in scene["beats"])
    scene["provider"] = provider
    scene["news"] = {"kind": ctx.kind, "query": ctx.query, "topic": ctx.topic, "grounded": ctx.grounded, "sources": len(items)}
    return scene


def headline_fallback(ctx: NewsContext) -> str:
    """Sem nenhum modelo para resumir: fala as manchetes como vieram, sem inventar nada."""
    items = pick_items(ctx.items)[:3]
    if not items:
        return "Não consegui buscar as notícias agora. Tente de novo em instantes."
    parts = [f"{it['outlet']}: {it['title']}." if it.get("outlet") else f"{it['title']}." for it in items]
    return "Estas são as principais manchetes. " + " ".join(parts)


async def _summarize_facts(messages: list[dict], ctx: NewsContext, persona: str) -> tuple[str, str]:
    """RSS (sem grounding): um modelo do projeto (llm.py, na ordem do LLM_ORDER) resume só os fatos encontrados."""
    try:
        import llm  # import tardio: este módulo continua testável sem httpx

        msgs = [m for m in inject_facts(messages, ctx) if m.get("role") != "system"][-6:]
        text, provider = await llm.complete(msgs, system=persona or None, max_tokens=450, temperature=0.3, timeout=LLM_TIMEOUT)
        return text, provider
    except Exception as exc:  # noqa: BLE001 - qualquer falha cai nas manchetes, nunca derruba a cena
        log.warning("Resumo das manchetes falhou (%s); falando as manchetes direto.", str(exc)[:200])
        return headline_fallback(ctx), "manchetes"


async def news_scene_for(messages: list[dict], persona: str = "") -> Optional[dict]:
    """Se a última fala pede notícias, devolve a cena pronta; senão None (e o fluxo normal segue).
    Nunca levanta exceção."""
    try:
        ctx = await prepare_news(messages, persona)
        if not ctx:
            return None
        provider = "gemini-search"
        text = ctx.answer
        if not text:
            text, provider = await _summarize_facts(messages, ctx, persona)
        text = clean_spoken(text or "")
        if not text:
            return None
        scene = build_scene(text, ctx, provider)
        log.info("Cena de notícias '%s': %d trechos, %d cartões (%s)", scene["title"], len(scene["beats"]), len(scene["media"]), provider)
        return scene
    except Exception:  # noqa: BLE001
        log.exception("Cena de notícias falhou; seguindo o fluxo normal.")
        return None
