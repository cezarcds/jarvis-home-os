"""Abre cada fonte e extrai título, veículo, data e imagem de capa (metatags Open Graph).
Não é print da página: é a imagem que o próprio veículo publica."""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import config
from .cache import TTLCache
from .safety import is_public_http_url_async

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JarvisHomeOS/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
_page_cache = TTLCache(ttl=config.PAGE_TTL, maxsize=512)

KNOWN_OUTLETS = {
    "folha.uol.com.br": "Folha de S.Paulo",
    "g1.globo.com": "g1",
    "oglobo.globo.com": "O Globo",
    "valor.globo.com": "Valor Econômico",
    "estadao.com.br": "Estadão",
    "infomoney.com.br": "InfoMoney",
    "uol.com.br": "UOL",
    "cnnbrasil.com.br": "CNN Brasil",
    "bbc.com": "BBC",
    "reuters.com": "Reuters",
    "exame.com": "Exame",
    "poder360.com.br": "Poder360",
    "metropoles.com": "Metrópoles",
    "terra.com.br": "Terra",
    "correiobraziliense.com.br": "Correio Braziliense",
    "agenciabrasil.ebc.com.br": "Agência Brasil",
    "tse.jus.br": "TSE",
    "camara.leg.br": "Câmara dos Deputados",
}


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            val = a.get("content")
            if key and val and key not in self.meta:
                self.meta[key] = val.strip()
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def parse_meta(html: str, base_url: str = "") -> dict:
    p = _MetaParser()
    try:
        p.feed(html[:400_000])
    except Exception:
        pass
    m = p.meta
    image = m.get("og:image") or m.get("og:image:url") or m.get("twitter:image") or ""
    if image and base_url:
        image = urljoin(base_url, image)
    if urlparse(image).scheme not in ("http", "https"):
        image = ""
    return {
        "title": (m.get("og:title") or m.get("twitter:title") or p.title or "").strip()[:220],
        "site_name": m.get("og:site_name", "").strip(),
        "image": image or None,
        "published": m.get("article:published_time") or m.get("og:article:published_time") or m.get("datepublished") or None,
    }


def outlet_from_url(url: str, fallback: str = "") -> str:
    host = (urlparse(url).hostname or fallback or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for dom, name in KNOWN_OUTLETS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host


async def fetch_html(url: str, max_bytes: int = 400_000, max_hops: int = 5):
    """Segue redirecionamentos manualmente, validando cada salto contra SSRF.
    Devolve (html|None, url_final)."""
    import httpx  # import tardio

    cur = url
    async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=4.0), follow_redirects=False, headers=HEADERS) as client:
        for _ in range(max_hops + 1):
            if not await is_public_http_url_async(cur):
                return None, cur
            async with client.stream("GET", cur) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        return None, cur
                    cur = urljoin(cur, loc)
                    continue
                if r.status_code >= 400 or "html" not in r.headers.get("content-type", "").lower():
                    return None, cur
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) >= max_bytes:
                        break
                return bytes(buf).decode(r.encoding or "utf-8", errors="replace"), cur
    return None, cur


async def enrich_source(uri: str, hint_outlet: str = "") -> dict:
    """uri pode ser o redirecionamento da busca do Google; devolvemos o link final do veículo."""
    cached = _page_cache.get(uri)
    if cached:
        return cached
    try:
        html, final = await fetch_html(uri)
    except Exception:
        html, final = None, uri
    meta = parse_meta(html, final) if html else {"title": "", "site_name": "", "image": None, "published": None}
    outlet = outlet_from_url(final, hint_outlet)
    if outlet == (urlparse(final).hostname or "").lower().replace("www.", "", 1) and meta["site_name"]:
        outlet = meta["site_name"]
    out = {
        "title": meta["title"] or f"Matéria de {outlet or 'veículo'}",
        "outlet": outlet or hint_outlet,
        "url": final,
        "published": meta["published"],
        "image": meta["image"],
    }
    _page_cache.set(uri, out)
    return out


async def enrich_many(sources: list[dict], concurrency: int = 4) -> list[dict]:
    """sources: [{"uri":..., "title": <domínio ou veículo>}]"""
    sem = asyncio.Semaphore(concurrency)

    async def one(s):
        async with sem:
            return await enrich_source(s["uri"], s.get("title", ""))

    results = await asyncio.gather(*(one(s) for s in sources), return_exceptions=True)
    seen, out = set(), []
    for res in results:
        if isinstance(res, dict) and res["url"] not in seen:
            seen.add(res["url"])
            out.append(res)
    return out
