"""Busca de imagens e vídeos contextuais para a mesa do JARVIS.

Fontes:
- Wikimedia Commons (sem chave): fotos e vídeos livres, com créditos e licença.
- YouTube Data API (opcional, YOUTUBE_API_KEY): vídeos incorporáveis, com
  SafeSearch estrito. Só é usado se a chave existir.

Nada aqui baixa mídia: o backend devolve apenas URLs e metadados, e o
navegador carrega o arquivo direto da origem.
"""
from __future__ import annotations

import html
import logging
import os
import re
import time

import httpx

log = logging.getLogger("jarvis.media")

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3/search"
USER_AGENT = "JarvisHomeOS/1.0 (projeto pessoal; assistente residencial)"

MEDIA_ENABLED = os.getenv("MEDIA_ENABLED", "true").strip().lower() not in {"0", "false", "no"}

# Filtro básico: arquivos cujo título/categorias tenham estes termos são descartados.
_BLOCKED = re.compile(
    r"\b(nude|nudity|naked|porn|nsfw|erotic|sex|sexual|gore|corpse|genital|fetish)\b", re.I
)
_TAGS = re.compile(r"<[^>]+>")

_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_CACHE_TTL = 60 * 60 * 6


def _clean_html(value: str | None, limit: int = 120) -> str:
    if not value:
        return ""
    return html.unescape(_TAGS.sub("", value)).strip()[:limit]


async def _commons(query: str, kind: str, limit: int = 8) -> list[dict]:
    filetype = "video" if kind == "video" else "bitmap"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:{filetype}",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1600",
        "iiextmetadatafilter": "Artist|LicenseShortName|ImageDescription|Categories",
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0, connect=6.0), headers={"User-Agent": USER_AGENT}
    ) as client:
        res = await client.get(COMMONS_API, params=params)
    res.raise_for_status()
    pages = (res.json().get("query") or {}).get("pages") or {}

    items = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            continue
        title = page.get("title", "").removeprefix("File:")
        meta = info.get("extmetadata") or {}
        categories = (meta.get("Categories") or {}).get("value", "")
        if _BLOCKED.search(title) or _BLOCKED.search(categories):
            continue
        mime = info.get("mime", "")
        width, height = info.get("width", 0), info.get("height", 0)
        if kind == "image":
            if mime not in {"image/jpeg", "image/png", "image/webp"}:
                continue
            if width < 800 or height < 450:  # evita miniaturas e ícones
                continue
            items.append({
                "kind": "image",
                "url": info.get("thumburl") or info.get("url"),
                "width": width,
                "height": height,
            })
        else:
            if not mime.startswith("video/"):
                continue
            items.append({
                "kind": "video",
                "src": info.get("url"),
                "poster": info.get("thumburl"),
                "width": width,
                "height": height,
            })
        items[-1].update({
            "title": title.rsplit(".", 1)[0][:90],
            "credit": _clean_html((meta.get("Artist") or {}).get("value"), 70) or "Wikimedia Commons",
            "license": _clean_html((meta.get("LicenseShortName") or {}).get("value"), 30),
            "page": info.get("descriptionshorturl") or info.get("descriptionurl"),
            "source": "Wikimedia Commons",
        })
    return items


async def _youtube(query: str, limit: int = 4) -> list[dict]:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        return []
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": str(limit),
        "videoEmbeddable": "true",
        "safeSearch": "strict",
        "videoDuration": "short",
        "relevanceLanguage": "pt",
        "key": key,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=6.0)) as client:
        res = await client.get(YOUTUBE_API, params=params)
    res.raise_for_status()
    items = []
    for it in res.json().get("items", []):
        vid = (it.get("id") or {}).get("videoId")
        sn = it.get("snippet") or {}
        if not vid or _BLOCKED.search(sn.get("title", "")):
            continue
        items.append({
            "kind": "video",
            "embed": f"https://www.youtube-nocookie.com/embed/{vid}",
            "poster": ((sn.get("thumbnails") or {}).get("high") or {}).get("url"),
            "title": _clean_html(sn.get("title"), 90),
            "credit": _clean_html(sn.get("channelTitle"), 60),
            "license": "YouTube",
            "page": f"https://www.youtube.com/watch?v={vid}",
            "source": "YouTube",
        })
    return items


async def search_media(query: str, kind: str = "image") -> dict | None:
    """Devolve o melhor resultado para a consulta, ou None."""
    if not MEDIA_ENABLED:
        return None
    query = query.strip()[:80]
    if not query:
        return None
    ck = (kind, query.lower())
    hit = _CACHE.get(ck)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1][0] if hit[1] else None

    results: list[dict] = []
    try:
        if kind == "video":
            results = await _youtube(query)
            if not results:
                results = await _commons(query, "video")
        else:
            results = await _commons(query, "image")
    except Exception as exc:  # mídia é um enfeite: nunca derruba a cena
        log.warning("Busca de mídia falhou (%s / %s): %s", kind, query, str(exc)[:200])
        return None

    _CACHE[ck] = (time.time(), results)
    return results[0] if results else None
