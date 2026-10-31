"""Leitura de feeds RSS/Atom. Sem chave: Google Notícias por padrão + feeds que você escolher."""
from __future__ import annotations
import asyncio
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from . import config
from .cache import TTLCache

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JarvisHomeOS/1.0)", "Accept": "application/rss+xml, application/xml, text/xml, */*"}
ATOM = "{http://www.w3.org/2005/Atom}"
_feed_cache = TTLCache(ttl=config.FEED_TTL)


def google_news_search_url(query: str, when: str | None = None) -> str:
    q = query.strip() + (f" when:{when}" if when else "")
    return f"https://news.google.com/rss/search?q={quote_plus(q)}&{config.GN_PARAMS}"


def google_news_top_url() -> str:
    return f"https://news.google.com/rss?{config.GN_PARAMS}"


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_rss(xml_text: str, limit: int = 10) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    channel_title = (root.findtext("channel/title") or "").strip()
    items: list[dict] = []

    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        src = it.find("source")
        outlet = (src.text or "").strip() if src is not None and src.text else ""
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -(len(outlet) + 3)].rstrip()
        if not outlet and "google" not in channel_title.lower():
            outlet = channel_title
        items.append({
            "id": item_id(link), "title": title, "outlet": outlet, "url": link,
            "published": _parse_date(it.findtext("pubDate")), "image": None,
        })

    for en in root.iter(f"{ATOM}entry"):
        title = (en.findtext(f"{ATOM}title") or "").strip()
        link_el = en.find(f"{ATOM}link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        if not title or not link:
            continue
        feed_title = (root.findtext(f"{ATOM}title") or "").strip()
        items.append({
            "id": item_id(link), "title": title, "outlet": feed_title, "url": link,
            "published": _parse_date(en.findtext(f"{ATOM}published") or en.findtext(f"{ATOM}updated")),
            "image": None,
        })
    return dedupe_sort(items, limit)


def dedupe_sort(items: list[dict], limit: int) -> list[dict]:
    seen, out = set(), []
    for it in sorted(items, key=lambda i: i.get("published") or "", reverse=True):
        key = "".join(ch for ch in it["title"].lower() if ch.isalnum())[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out


async def fetch_feed(url: str, limit: int = 10) -> list[dict]:
    cached = _feed_cache.get(url)
    if cached is not None:
        return cached[:limit]
    import httpx  # import tardio: facilita testes sem rede

    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=True, headers=HEADERS) as client:
        r = await client.get(url)
        r.raise_for_status()
        items = parse_rss(r.text, limit=50)
    _feed_cache.set(url, items)
    return items[:limit]


def topic_urls(topic: str) -> list[str]:
    urls: list[str] = []
    spec = config.TOPICS.get(topic)
    if spec:
        urls.append(google_news_search_url(spec["query"], spec["when"]) if spec["query"] else google_news_top_url())
    urls.extend(config.extra_feeds().get(topic, []))
    return urls


def topic_catalog() -> list[dict]:
    keys = list(config.TOPICS) + [k for k in config.extra_feeds() if k not in config.TOPICS]
    return [{"key": k, "label": config.TOPICS.get(k, {}).get("label") or k.title()} for k in keys]


async def get_topic(topic: str, limit: int = 8) -> list[dict]:
    urls = topic_urls(topic)
    if not urls:
        return []
    results = await asyncio.gather(*(fetch_feed(u, 30) for u in urls), return_exceptions=True)
    merged: list[dict] = []
    for res in results:
        if isinstance(res, list):
            merged.extend(res)
    return dedupe_sort(merged, limit)
