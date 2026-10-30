"""Contexto factual para o diretor de cena.

Modelos pequenos inventam fatos com segurança (ex.: pôr Angra 1, 2 e 3 na
Paraíba). Antes de dirigir a cena, buscamos na Wikipédia em português os
primeiros parágrafos e as coordenadas dos assuntos da pergunta, e entregamos ao
modelo como "fatos de referência". Se a busca falhar, a cena segue sem isso.

Variáveis de ambiente:
  GROUNDING_ENABLED  "false" desliga (padrão: ligado)
"""
from __future__ import annotations

import logging
import os
import re
import time

import media as _media  # reaproveita o cliente HTTP e o User-Agent com contato

log = logging.getLogger("jarvis.grounding")

WIKI_API = "https://pt.wikipedia.org/w/api.php"
GROUNDING_ENABLED = os.getenv("GROUNDING_ENABLED", "true").strip().lower() not in {"0", "false", "no"}

_CACHE: dict[str, tuple[float, str]] = {}
_TTL_HIT = 60 * 60 * 6
_TTL_MISS = 60 * 5

# Tira o pedido ("me mostre", "explique", "jarvis,") e deixa só o assunto.
_LEAD = re.compile(
    r"^\s*(?:(?:ei|oi|ok)\s+)?(?:jarvis[\s,]+)?"
    r"(?:(?:me|nos)\s+)?"
    r"(?:mostr[ae]|explique|explica|fal[ae](?:\s+sobre)?|cont[ae]|dig[ae]|desenh[ae]|list[ae]|compar[ae]|"
    r"pesquis[ae]|busque|busca|visualiz[ae]|ilustr[ae]|abr[ae])?\s*"
    r"(?:(?:os|as|o|a|um|uma|sobre|de|do|da|dos|das)\s+)*"
    r"(?:(?:o\s+que\s+(?:é|são|e|sao)|como\s+funciona[m]?|quais\s+(?:são|sao)|qual\s+(?:é|e)|quem\s+(?:é|foi|e)|onde\s+(?:fica[m]?|está|estão))\s+)?"
    r"(?:(?:os|as|o|a|um|uma|de|do|da|dos|das)\s+)*",
    re.I,
)


def topic_of(question: str) -> str:
    t = _LEAD.sub("", (question or "").strip())
    t = re.sub(r"[?!.…]+$", "", t).strip()
    return t[:100]


async def fetch_context(question: str, max_pages: int = 2, per_page: int = 900) -> str:
    """Texto com até `max_pages` verbetes (título, resumo, coordenadas). Vazio se nada serve."""
    if not GROUNDING_ENABLED:
        return ""
    topic = topic_of(question)
    if len(topic) < 4:
        return ""

    key = topic.lower()
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < (_TTL_HIT if hit[1] else _TTL_MISS):
        return hit[1]

    started = time.time()
    text = ""
    try:
        async with _media._client() as client:
            res = await client.get(WIKI_API, params={
                "action": "query", "format": "json", "redirects": "1",
                "generator": "search", "gsrsearch": topic, "gsrnamespace": "0", "gsrlimit": "3",
                "prop": "extracts|coordinates", "exintro": "1", "explaintext": "1",
                "exchars": str(per_page), "exlimit": "3", "colimit": "3",
            })
            res.raise_for_status()
            pages = list(((res.json().get("query") or {}).get("pages") or {}).values())
        pages.sort(key=lambda p: p.get("index", 99))
        lines = []
        for p in pages:
            extract = re.sub(r"\s+", " ", p.get("extract") or "").strip()
            if not extract:
                continue
            line = f"- {p.get('title', '')}: {extract}"
            coords = (p.get("coordinates") or [None])[0]
            if coords and "lat" in coords and "lon" in coords:
                line += f" [coordenadas: {coords['lat']:.3f}, {coords['lon']:.3f}]"
            lines.append(line)
            if len(lines) >= max_pages:
                break
        text = "\n".join(lines)
    except Exception as exc:  # noqa: BLE001 - contexto é um reforço, nunca derruba a cena
        log.warning("Contexto factual indisponível (%s): %s", topic, str(exc)[:160])
        return ""  # falha de rede não vai para o cache

    _CACHE[key] = (time.time(), text)
    log.info("Contexto factual '%s': %d verbete(s) em %.2fs", topic, text.count("\n") + 1 if text else 0, time.time() - started)
    return text
