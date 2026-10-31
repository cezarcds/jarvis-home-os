"""Detecta, em português, quando a fala pede notícias.

Três níveis, para evitar falso positivo ("o que aconteceu com o Império Romano?" não é notícia):
  1. Forte: palavras como "notícias", "manchetes", "últimas do mercado".
  2. Condicional: "o que aconteceu / como foi" só conta junto de tempo (hoje, domingo...) ou assunto quente.
  3. Fraco: assunto quente (eleição, dólar, Selic...) + tempo.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from . import config


def norm(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


DIAS = r"(domingo|segunda|terca|quarta|quinta|sexta|sabado)"
TEMPORAL = re.compile(
    rf"\b(hoje|ontem|anteontem|agora|{DIAS}|ultimo|ultima|ultimos|ultimas|"
    r"(essa|esta|nessa|nesta) semana|recente|recentes|ha pouco|esta manha|essa manha|de manha)\b"
)

HOT_TOPICS = re.compile(
    r"\b(eleicao|eleicoes|ibovespa|dolar|bolsa|selic|copom|juros|inflacao|ipca|pib|"
    r"congresso|senado|camara|stf|tse|lula|bolsonaro|governo|guerra|bitcoin|petrobras|acoes)\b"
)
MARKET = re.compile(r"\b(ibovespa|dolar|bolsa|selic|copom|juros|inflacao|ipca|pib|acoes|bitcoin|petrobras|mercado)\b")
POLITICS = re.compile(r"\b(eleicao|eleicoes|congresso|senado|camara|stf|tse|lula|bolsonaro|governo|politica|partido)\b")

STRONG = [
    re.compile(r"\bnoticias?\b"),
    re.compile(r"\bmanchetes?\b"),
    re.compile(r"\bnovidades? (sobre|de|do|da|no|na)\b"),
    re.compile(r"\bultimas? (sobre|do|da|de|no|na|noticias|novidades)\b"),
    re.compile(r"\bme (atualiza|atualize|poe|ponha) (sobre|por dentro)\b"),
]
CONDITIONAL = [
    re.compile(r"\bo que (aconteceu|rolou|houve|saiu|mudou)\b"),
    re.compile(r"\bo que (esta|ta) (acontecendo|rolando)\b"),
    re.compile(r"\bcomo (foi|ficou|terminou|acabou|fechou|abriu)\b"),
    re.compile(r"\bquem (ganhou|venceu|foi eleito)\b"),
    re.compile(r"\bresultado (da|do|das|dos)\b"),
]
NOT_NEWS = re.compile(r"\b(boa|ma|pessima|otima|triste) noticia\b")
BRIEFING = re.compile(r"^\s*(jarvis[ ,]*)?(bom dia|resumo do dia|briefing|manchetes do dia|o que tem de novo)\b")

STOPWORDS = set(
    "jarvis me conta contar diz dizer fala falar quero queria gostaria saber sobre de do da dos das no na nos nas "
    "o a os as um uma e que qual quais foi ficou aconteceu rolou houve saiu mudou esta ta estao "
    "acontecendo rolando noticia noticias manchete manchetes ultima ultimas ultimo ultimos novidade novidades "
    "pra para por com em ao aos sobre ai ja ver mostra mostre traga traz busca busque pesquisa pesquise "
    "hoje ontem agora recente recentes".split()
)


@dataclass
class Intent:
    kind: str            # "search" | "briefing"
    query: str           # texto original (vai para a busca com Google Search)
    short_query: str     # termos enxutos (vão para o RSS de busca)
    topic: Optional[str]
    when: str            # janela de recência para o RSS: 1d | 7d


def _short_query(text: str) -> str:
    kept = []
    for raw in re.findall(r"[\wÀ-ÿ]+", text):
        if norm(raw) not in STOPWORDS and len(raw) > 1:
            kept.append(raw)
    return " ".join(kept) or text.strip()


def _topic(n: str) -> Optional[str]:
    if MARKET.search(n):
        return "mercado"
    if POLITICS.search(n):
        return "politica"
    return None


def detect(text: str) -> Optional[Intent]:
    if not text or not text.strip():
        return None
    n = norm(text)
    scrub = NOT_NEWS.sub(" ", n)
    has_time = bool(TEMPORAL.search(n))
    has_hot = bool(HOT_TOPICS.search(n))

    is_search = (
        any(p.search(scrub) for p in STRONG)
        or (any(p.search(n) for p in CONDITIONAL) and (has_time or has_hot))
        or (has_hot and has_time)
    )
    if is_search:
        when = "1d" if re.search(r"\b(hoje|agora|ha pouco|esta manha|essa manha|de manha)\b", n) else "7d"
        return Intent("search", text.strip(), _short_query(text), _topic(n), when)

    if config.briefing_on_greeting() and BRIEFING.search(n):
        return Intent("briefing", text.strip(), "", None, "1d")
    return None
