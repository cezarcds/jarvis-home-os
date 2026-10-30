"""Palavra de ativação: acha "Jarvis" (e as variações que o Whisper costuma escrever) no começo ou no fim da frase."""
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

_TRIM = " ,.:;!?-—–…\"'"
_ARTIFACTS = re.compile(
    r"(legendas? (pela|por|da)|amara\.org|transcri[cç][aã]o e legendas|inscreva-se|obrigado por assistir)", re.IGNORECASE
)
# Frases que o Whisper "inventa" em silêncio/ruído.
_HALLUCINATIONS = {"", "e", "ah", "uh", "hm", "hmm", "tchau", "tchau tchau", "ate a proxima", "obrigado por assistir"}


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def clean_text(text: str) -> str:
    """Remove lixo típico do Whisper; devolve '' se não sobrou fala de verdade."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t or _ARTIFACTS.search(t):
        return ""
    if _strip_accents(t).strip(_TRIM) in _HALLUCINATIONS:
        return ""
    return t


@dataclass
class WakeMatch:
    command: str   # o que foi dito além da palavra de ativação ("" se só chamou)
    heard: str     # como a palavra foi escrita ("Jarvis", "Garvis"...)


def _is_wake(token: str, wake: str) -> bool:
    t = _strip_accents(token)
    if len(t) < 4:
        return False
    return t == wake or SequenceMatcher(None, t, wake).ratio() >= 0.8


_GREETINGS = {"ei", "oi", "ok", "ola", "hey", "e", "fala", "opa", "salve", "eai"}


def find_wake(text: str, wake_word: str = "jarvis") -> Optional[WakeMatch]:
    """Procura a palavra nas 4 primeiras palavras ("ei, Jarvis, abre o Profit") ou nas 2 últimas
    ("abre o Profit, Jarvis"). Em qualquer outro lugar da frase é só alguém citando o nome."""
    wake = _strip_accents(wake_word)
    toks = list(re.finditer(r"[\wÀ-ÿ]+", text or ""))
    if not toks:
        return None
    for i, m in enumerate(toks[:4]):
        if not _is_wake(m.group(), wake):
            continue
        antes = [_strip_accents(t.group()) for t in toks[:i]]
        so_cumprimento = all(a in _GREETINGS for a in antes)
        if not so_cumprimento and i >= len(toks) - 2:  # "abre o profit, jarvis": o nome veio no fim
            return WakeMatch(text[:m.start()].strip(_TRIM), m.group())
        return WakeMatch(text[m.end():].strip(_TRIM), m.group())
    if len(toks) >= 3:
        for m in toks[-2:]:
            if _is_wake(m.group(), wake):
                return WakeMatch(text[:m.start()].strip(_TRIM), m.group())
    return None
