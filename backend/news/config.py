"""Configuração do módulo de notícias. Tudo lido de forma preguiçosa (na hora do uso),
para respeitar o .env carregado pelo main.py, não importa a ordem dos imports."""
from __future__ import annotations
import os
from datetime import timedelta, timezone

# Brasil não tem horário de verão desde 2019: offset fixo evita depender de tzdata no Windows.
TZ_BR = timezone(timedelta(hours=-3))

GN_PARAMS = "hl=pt-BR&gl=BR&ceid=BR:pt-419"

# Tópicos prontos. "query" vira busca no Google Notícias RSS; sem query = principais manchetes.
TOPICS = {
    "mercado": {
        "label": "Mercado",
        "query": "Ibovespa OR dólar OR Selic OR bolsa de valores",
        "when": "1d",
    },
    "brasil": {"label": "Brasil", "query": None, "when": None},
    "politica": {
        "label": "Política",
        "query": "política Brasil governo Congresso STF",
        "when": "1d",
    },
    "tecnologia": {
        "label": "Tecnologia",
        "query": "tecnologia OR inteligência artificial",
        "when": "1d",
    },
}

# Ordem do resumo "bom dia": mercado primeiro (você usa o Profit).
BRIEFING_TOPICS = ["mercado", "brasil"]
BRIEFING_PER_TOPIC = 4


def enabled() -> bool:
    return os.getenv("NEWS_ENABLED", "1").strip() != "0"


def briefing_on_greeting() -> bool:
    return os.getenv("NEWS_BRIEFING_ON_GREETING", "1").strip() != "0"


def gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def gemini_model() -> str:
    name = (
        os.getenv("NEWS_GEMINI_MODEL", "").strip()
        or os.getenv("GEMINI_MODEL", "").strip()
        or "gemini-2.5-flash"
    )
    # Aceita o formato do litellm ("gemini/gemini-...") e o nome puro da API.
    for prefix in ("gemini/", "models/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def extra_feeds() -> dict:
    """NEWS_EXTRA_FEEDS="mercado=https://site/rss,mercado=https://outro/rss,cripto=https://x/rss"
    A mesma chave várias vezes junta os feeds no mesmo tópico."""
    out: dict = {}
    for pair in os.getenv("NEWS_EXTRA_FEEDS", "").split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        key, url = pair.split("=", 1)
        key, url = key.strip().lower(), url.strip()
        if key and url.startswith(("http://", "https://")):
            out.setdefault(key, []).append(url)
    return out


FEED_TTL = 600      # 10 min
SEARCH_TTL = 600    # 10 min
PAGE_TTL = 6 * 3600  # metadados de página: 6 h
SEARCH_TIMEOUT = 25  # teto total da pesquisa (segundos)
