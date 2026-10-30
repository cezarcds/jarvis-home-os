"""Busca de imagens e vídeos contextuais para a mesa do JARVIS.

Cadeia de fontes (a primeira que devolver algo vence):

  imagens: Wikimedia Commons -> Openverse -> Pexels* -> Pixabay*
  vídeos : YouTube* -> Pexels* -> Pixabay* -> Wikimedia Commons
  (* só entram se a chave existir: YOUTUBE_API_KEY, PEXELS_API_KEY, PIXABAY_API_KEY)

Variáveis de ambiente úteis:
  MEDIA_CONTACT      contato que vai no User-Agent (URL ou e-mail). O Wikimedia
                     bloqueia (403) clientes sem identificação com contato.
  MEDIA_USER_AGENT   sobrescreve o User-Agent inteiro.
  MEDIA_ENABLED      "false" desliga a busca de mídia.

Nada aqui baixa mídia: o backend devolve apenas URLs e metadados, e o
navegador carrega o arquivo direto da origem.
"""
from __future__ import annotations

import html
import logging
import os
import re
import time
from typing import Awaitable, Callable

import httpx

log = logging.getLogger("jarvis.media")

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
PEXELS_PHOTOS = "https://api.pexels.com/v1/search"
PEXELS_VIDEOS = "https://api.pexels.com/videos/search"
PIXABAY_PHOTOS = "https://pixabay.com/api/"
PIXABAY_VIDEOS = "https://pixabay.com/api/videos/"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3/search"


def _user_agent() -> str:
    """User-Agent no formato pedido pelo Wikimedia: Nome/versão (contato) biblioteca."""
    custom = os.getenv("MEDIA_USER_AGENT", "").strip()
    if custom:
        return custom
    contact = os.getenv("MEDIA_CONTACT", "").strip() or "https://github.com/cezarcds/jarvis-home-os"
    return f"JarvisHomeOS/1.0 ({contact}) httpx/{getattr(httpx, '__version__', '0')}"


MEDIA_ENABLED = os.getenv("MEDIA_ENABLED", "true").strip().lower() not in {"0", "false", "no"}

# Filtro básico: arquivos cujo título/categorias tenham estes termos são descartados.
_BLOCKED = re.compile(
    r"\b(nude|nudity|naked|porn|nsfw|erotic|sex|sexual|gore|corpse|genital|fetish)\b", re.I
)
_TAGS = re.compile(r"<[^>]+>")

# Cache: resultado bom dura horas; "nada encontrado" dura pouco, para não
# esconder um erro passageiro por seis horas.
_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_TTL_HIT = 60 * 60 * 6
_TTL_MISS = 60 * 3

# Provedor que respondeu 403/429 fica de molho por um tempo, em vez de ser
# martelado a cada cena.
_COOLDOWN: dict[str, float] = {}
_COOLDOWN_SECS = 60 * 10


def _clean_html(value: str | None, limit: int = 120) -> str:
    if not value:
        return ""
    return html.unescape(_TAGS.sub("", value)).strip()[:limit]


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=6.0),
        headers={"User-Agent": _user_agent(), "Accept": "application/json"},
        follow_redirects=True,
    )


def _key(name: str) -> str:
    return os.getenv(name, "").strip()


# --------------------------------------------------------------------------
# Provedores. Cada um devolve uma lista de itens já no formato do front-end.
# --------------------------------------------------------------------------

async def _commons(client, query: str, kind: str, limit: int = 8) -> list[dict]:
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
            item = {"kind": "image", "url": info.get("thumburl") or info.get("url"),
                    "width": width, "height": height}
        else:
            if not mime.startswith("video/"):
                continue
            item = {"kind": "video", "src": info.get("url"), "poster": info.get("thumburl"),
                    "width": width, "height": height}
        item.update({
            "title": title.rsplit(".", 1)[0][:90],
            "credit": _clean_html((meta.get("Artist") or {}).get("value"), 70) or "Wikimedia Commons",
            "license": _clean_html((meta.get("LicenseShortName") or {}).get("value"), 30),
            "page": info.get("descriptionshorturl") or info.get("descriptionurl"),
            "source": "Wikimedia Commons",
        })
        items.append(item)
    return items


async def _openverse(client, query: str, kind: str, limit: int = 8) -> list[dict]:
    if kind != "image":
        return []
    res = await client.get(OPENVERSE_API, params={
        "q": query, "page_size": str(limit), "mature": "false", "aspect_ratio": "wide",
    })
    res.raise_for_status()
    items = []
    for r in res.json().get("results") or []:
        title = _clean_html(r.get("title"), 90)
        if _BLOCKED.search(title):
            continue
        url, thumb = r.get("url") or "", r.get("thumbnail") or ""
        if not url.startswith("https://"):  # evita conteúdo misto no navegador
            url = thumb
        if not url:
            continue
        lic = " ".join(x for x in (str(r.get("license") or "").upper(), r.get("license_version") or "") if x)
        items.append({
            "kind": "image",
            "url": url,
            "fallback_url": thumb or None,  # o front pode usar em onError (hotlink bloqueado)
            "width": r.get("width") or 0,
            "height": r.get("height") or 0,
            "title": title,
            "credit": _clean_html(r.get("creator"), 70) or str(r.get("source") or "Openverse"),
            "license": lic[:30],
            "page": r.get("foreign_landing_url"),
            "source": "Openverse",
        })
    return items


async def _pexels(client, query: str, kind: str, limit: int = 8) -> list[dict]:
    key = _key("PEXELS_API_KEY")
    if not key:
        return []
    headers = {"Authorization": key}
    params = {"query": query, "per_page": str(limit), "orientation": "landscape"}
    if kind == "video":
        res = await client.get(PEXELS_VIDEOS, params=params, headers=headers)
        res.raise_for_status()
        items = []
        for v in res.json().get("videos") or []:
            files = [f for f in (v.get("video_files") or [])
                     if str(f.get("file_type", "")).endswith("mp4") and f.get("link")]
            files = [f for f in files if (f.get("width") or 0) <= 1920] or files
            if not files:
                continue
            best = max(files, key=lambda f: min(f.get("width") or 0, 1280))
            items.append({
                "kind": "video", "src": best["link"], "poster": v.get("image"),
                "width": best.get("width") or 0, "height": best.get("height") or 0,
                "title": f"Pexels {v.get('id')}",
                "credit": _clean_html((v.get("user") or {}).get("name"), 60) or "Pexels",
                "license": "Pexels", "page": v.get("url"), "source": "Pexels",
            })
        return items
    res = await client.get(PEXELS_PHOTOS, params=params, headers=headers)
    res.raise_for_status()
    items = []
    for p in res.json().get("photos") or []:
        src = p.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            continue
        items.append({
            "kind": "image", "url": url, "width": p.get("width") or 0, "height": p.get("height") or 0,
            "title": _clean_html(p.get("alt"), 90) or "Pexels",
            "credit": _clean_html(p.get("photographer"), 60) or "Pexels",
            "license": "Pexels", "page": p.get("url"), "source": "Pexels",
        })
    return items


async def _pixabay(client, query: str, kind: str, limit: int = 8) -> list[dict]:
    key = _key("PIXABAY_API_KEY")
    if not key:
        return []
    params = {"key": key, "q": query, "per_page": str(max(3, limit)), "safesearch": "true"}
    if kind == "video":
        res = await client.get(PIXABAY_VIDEOS, params=params)
        res.raise_for_status()
        items = []
        for h in res.json().get("hits") or []:
            vids = h.get("videos") or {}
            v = vids.get("medium") or vids.get("small") or vids.get("large") or {}
            if not v.get("url"):
                continue
            items.append({
                "kind": "video", "src": v["url"],
                "poster": f"https://i.vimeocdn.com/video/{h.get('picture_id')}_640x360.jpg" if h.get("picture_id") else None,
                "width": v.get("width") or 0, "height": v.get("height") or 0,
                "title": _clean_html(h.get("tags"), 90) or "Pixabay",
                "credit": _clean_html(h.get("user"), 60) or "Pixabay",
                "license": "Pixabay", "page": h.get("pageURL"), "source": "Pixabay",
            })
        return items
    params.update({"image_type": "photo", "orientation": "horizontal"})
    res = await client.get(PIXABAY_PHOTOS, params=params)
    res.raise_for_status()
    items = []
    for h in res.json().get("hits") or []:
        url = h.get("largeImageURL") or h.get("webformatURL")
        if not url:
            continue
        items.append({
            "kind": "image", "url": url, "width": h.get("imageWidth") or 0, "height": h.get("imageHeight") or 0,
            "title": _clean_html(h.get("tags"), 90) or "Pixabay",
            "credit": _clean_html(h.get("user"), 60) or "Pixabay",
            "license": "Pixabay", "page": h.get("pageURL"), "source": "Pixabay",
        })
    return items


async def _youtube(client, query: str, kind: str, limit: int = 4) -> list[dict]:
    key = _key("YOUTUBE_API_KEY")
    if not key or kind != "video":
        return []
    res = await client.get(YOUTUBE_API, params={
        "part": "snippet", "type": "video", "q": query, "maxResults": str(limit),
        "videoEmbeddable": "true", "safeSearch": "strict", "videoDuration": "short",
        "relevanceLanguage": "pt", "key": key,
    })
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


Provider = Callable[..., Awaitable[list]]

_IMAGE_CHAIN: list[tuple[str, Provider]] = [
    ("commons", _commons), ("openverse", _openverse), ("pexels", _pexels), ("pixabay", _pixabay),
]
_VIDEO_CHAIN: list[tuple[str, Provider]] = [
    ("youtube", _youtube), ("pexels", _pexels), ("pixabay", _pixabay), ("commons", _commons),
]


# Provedores que só funcionam com chave: sem ela, nem tentam (evita requisição à toa).
_NEEDS_KEY = {"youtube": "YOUTUBE_API_KEY", "pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}


def _variants(query: str) -> list[str]:
    """Consulta original e versões cada vez mais genéricas.

    Bancos de fotos não têm "angra 2 cooling towers", mas têm "cooling towers".
    Ordem: original, sem números, 3 primeiras palavras, 2 últimas, 2 primeiras.
    """
    words = query.split()
    plain = [w for w in words if not w.isdigit()]
    cands = [
        query,
        " ".join(plain),
        " ".join(plain[:3]),
        " ".join(plain[-2:]),
        " ".join(plain[:2]),
    ]
    out: list[str] = []
    for c in cands:
        c = c.strip()
        if len(c) >= 3 and c not in out:
            out.append(c)
    return out[:5]


def _fmt_error(exc: Exception) -> str:
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    return f"HTTP {status}" if status else f"{type(exc).__name__}: {str(exc)[:80]}"


async def _run_chain(query: str, kind: str, tried: list[str]) -> list[dict]:
    chain = _VIDEO_CHAIN if kind == "video" else _IMAGE_CHAIN
    async with _client() as client:
        for variant in _variants(query):
            for name, fn in chain:
                if _COOLDOWN.get(name, 0) > time.time():
                    continue
                if name in _NEEDS_KEY and not _key(_NEEDS_KEY[name]):
                    continue
                try:
                    items = await fn(client, variant, kind)
                except Exception as exc:  # noqa: BLE001 - um provedor ruim não derruba os outros
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status in (403, 429):
                        _COOLDOWN[name] = time.time() + _COOLDOWN_SECS
                    tried.append(f"{name}[{variant}]: {_fmt_error(exc)}")
                    log.warning("Mídia: %s falhou (%s / %s): %s", name, kind, variant, _fmt_error(exc))
                    continue
                if items:
                    tried.append(f"{name}[{variant}]: ok ({len(items)})")
                    return items
                tried.append(f"{name}[{variant}]: vazio")
    return []


async def search_media_all(query: str, kind: str = "image") -> tuple[list[dict], list[str]]:
    """Devolve (todos os candidatos do primeiro provedor que respondeu, histórico das tentativas).

    O front-end tenta os candidatos em ordem: se a primeira imagem não carregar
    (hotlink bloqueado, link morto), usa a seguinte em vez de ficar sem imagem.
    """
    if not MEDIA_ENABLED:
        return [], ["MEDIA_ENABLED=false"]
    query = query.strip()[:80]
    if not query:
        return [], []
    ck = (kind, query.lower())
    hit = _CACHE.get(ck)
    if hit:
        ttl = _TTL_HIT if hit[1] else _TTL_MISS
        if time.time() - hit[0] < ttl:
            return list(hit[1]), ["cache"]

    tried: list[str] = []
    results = await _run_chain(query, kind, tried)
    # Só guarda "nada encontrado" quando nenhum provedor deu erro (senão é falha, não ausência).
    if results or not any("HTTP" in t or "Error" in t for t in tried):
        _CACHE[ck] = (time.time(), results)
    if not results:
        log.warning("Mídia sem resultado (%s / %s): %s", kind, query, "; ".join(tried))
    return results, tried


async def search_media_detailed(query: str, kind: str = "image") -> tuple[dict | None, list[str]]:
    """Devolve (melhor item ou None, histórico das tentativas)."""
    results, tried = await search_media_all(query, kind)
    return (results[0] if results else None), tried


async def search_media(query: str, kind: str = "image") -> dict | None:
    """Compatível com o código antigo: devolve só o item."""
    item, _ = await search_media_detailed(query, kind)
    return item


async def diagnose(query: str = "nuclear power plant") -> dict:
    """Testa cada provedor isoladamente (ignora cache e cooldown) para achar o que está falhando."""
    report: dict = {"user_agent": _user_agent(), "providers": {}}
    async with _client() as client:
        for kind, chain in (("image", _IMAGE_CHAIN), ("video", _VIDEO_CHAIN)):
            for name, fn in chain:
                label = f"{name}:{kind}"
                try:
                    items = await fn(client, query, kind)
                    report["providers"][label] = {"ok": True, "results": len(items)}
                except Exception as exc:  # noqa: BLE001
                    report["providers"][label] = {"ok": False, "error": _fmt_error(exc)}
    return report