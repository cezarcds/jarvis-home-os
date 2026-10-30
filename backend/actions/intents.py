"""Interpreta pedidos falados de ação e de visão (regras simples, sem LLM: rápido e previsível)."""
import re
from dataclasses import dataclass
from typing import Optional

from routines.textutil import normalize

_PREFIXOS = r"(?:(?:por favor|pode|poderia|consegue|quero|queria|preciso|vou querer|agora|entao)\s+)*(?:me\s+)?"
_OPEN_VERBS = r"(?:abr(?:e|a|ir|o)|inicia(?:r)?|inicie|execut(?:a|ar|e)|lanc(?:a|ar|e))"
_OPEN_RE = re.compile(
    rf"^{_PREFIXOS}{_OPEN_VERBS}\s+(?:(?:o|a|os|as|um|uma)\s+)?(?:(?:programa|aplicativo|app)\s+)?(?P<app>[a-z0-9 ]+?)"
    rf"(?:\s+(?:pra mim|para mim|por favor|agora))*$"
)
_SOLO_RE = re.compile(r"\b(sozinho|em tela cheia|tela cheia|sem dividir|sem organizar|sem layout)\b")
_SPLIT_RE = re.compile(r"\b(dividindo|dividido|lado a lado|do lado|organizando|com voce)\b")
_NOT_APPS = re.compile(
    r"\b(rotina|rotinas|painel|admin|configuracao|configuracoes|conversa|mapa|imagem|foto|fotos|video|videos|"
    r"diagrama|grafico|desenho|janela de conversa)\b"
)


@dataclass
class OpenIntent:
    app: str
    organize: bool = True
    app_words: int = 1


def parse_open(text: str) -> Optional[OpenIntent]:
    q = normalize(text)
    if not q:
        return None
    organize = True
    if _SOLO_RE.search(q):
        organize = False
    q2 = _SPLIT_RE.sub("", _SOLO_RE.sub("", q))
    q2 = re.sub(r"\s+", " ", q2).strip()
    m = _OPEN_RE.match(q2)
    if not m:
        return None
    app = m.group("app").strip()
    if not app or _NOT_APPS.search(app):
        return None
    return OpenIntent(app=app, organize=organize, app_words=len(app.split()))


_ARRANGE_RE = re.compile(
    r"^(?:(?:por favor|pode|poderia|agora)\s+)*(?:organiz(?:a|ar|e)|arrum(?:a|ar|e)|dividir?|divid(?:a|e)|ajust(?:a|ar|e)|"
    r"reorganiz(?:a|ar|e))\s+(?:(?:a|as|minha|minhas|essa|esta)\s+)*(?:tela|janelas?)(?:\s+(?:pra mim|para mim|por favor))?$"
)
_FULL_RE = re.compile(
    r"^(?:(?:por favor|pode|poderia|agora)\s+)*(?:(?:me da|me de|quero|volta|voltar|restaura|restaurar|expande|expandir|"
    r"maximiza|maximizar|ocupa|ocupar)\s+)?(?:a\s+|o\s+)?(?:tela\s+(?:toda|inteira|cheia)|jarvis\s+(?:em\s+)?tela\s+cheia|"
    r"jarvis\s+(?:na\s+)?tela\s+toda|tela\s+cheia|tela\s+normal|(?:a\s+)?tela\s+toda)(?:\s+(?:pra mim|para mim|por favor))?$"
)


def parse_layout(text: str) -> Optional[str]:
    """'arrange' (reaplicar 2/3 e 1/3 na janela em foco) | 'jarvis_full' | None."""
    q = normalize(text)
    if _ARRANGE_RE.match(q):
        return "arrange"
    if _FULL_RE.match(q) or q in ("restaurar jarvis", "restaura o jarvis", "volta o jarvis", "jarvis tela cheia"):
        return "jarvis_full"
    return None


# ---------- Visão ----------

_SCREEN = r"(?:tela|janela|monitor)"
_ONCE_RES = [
    re.compile(rf"\b(?:olha|olhe|olhar|veja|ve|ver|enxerga|observa|observe|confere|confira|le)\b.*\b{_SCREEN}\b"),
    re.compile(r"\bo que (?:voce )?(?:esta|ta|tem|ha) (?:vendo|na tela|aqui na tela|aparecendo)\b"),
    re.compile(r"\b(?:olha|olhe|veja|ve|analisa|analise|analisar)\b.*\b(?:isso|isto|aqui|esse|este|essa|esta|grafico|candle|candles)\b"),
    re.compile(r"\b(?:analisa|analise|analisar|interpreta|interprete|comenta|comente)\b.*\b(?:tela|grafico|janela)\b"),
    re.compile(r"\bo que (?:voce )?acha (?:disso|desse|deste|desta|dessa|do grafico|da tela)\b"),
    re.compile(r"\b(?:me )?(?:descreve|descreva|explica|explique)\b.*\b(?:tela|grafico)\b"),
]
_ON_RES = [
    re.compile(r"\b(?:modo|ativa(?:r)?|liga(?:r)?|entra(?:r)? no modo)\b.*\b(?:analise|copiloto|co piloto|acompanhamento|acompanhar)\b"),
    re.compile(r"\b(?:analisa|analise|analisar|acompanha|acompanhe|acompanhar|fica|fique|ficar) (?:comigo|olhando|de olho|vendo)\b"),
    re.compile(r"\bvamos analisar\b.*\bjuntos?\b"),
    re.compile(r"\b(?:acompanha|acompanhe|acompanhar|observa|observe)\b.*\b(?:minha tela|o grafico|a tela)\b"),
]
_OFF_RES = [
    re.compile(r"\b(?:para|pare|parar|chega|deixa|deixe) de (?:olhar|ver|vendo|olhando|acompanhar|analisar)\b"),
    re.compile(r"\b(?:desliga|desligue|desligar|encerra|encerre|encerrar|cancela|cancele|sai|sair|saia)\b.*"
               r"\b(?:modo|analise|visao|copiloto|co piloto|acompanhamento)\b"),
    re.compile(r"\b(?:esquece|esqueca|esquecer)\b.*\b(?:tela|isso|imagem|captura)\b"),
    re.compile(r"\bnao precisa mais (?:olhar|ver)\b"),
]
_LOOK_APP = re.compile(r"^(?:olha|olhe|veja|ve|confere|confira)\s+(?:(?:o|a|no|na|pro|pra)\s+)?(?P<app>[a-z0-9 ]{2,30})$")
_APP_AFTER = re.compile(r"\b(?:no|na|do|da|de|pro|pra|para o|para a)\s+(?P<app>[a-z0-9 ]{2,30})$")


@dataclass
class VisionIntent:
    kind: str                     # "once" | "on" | "off"
    target_hint: Optional[str] = None


def parse_vision(text: str) -> Optional[VisionIntent]:
    q = normalize(text)
    if not q:
        return None
    # "off" primeiro: "para de olhar a tela" também casaria com "once".
    if any(r.search(q) for r in _OFF_RES):
        return VisionIntent("off")
    if any(r.search(q) for r in _ON_RES):
        return VisionIntent("on", _hint(q))
    if any(r.search(q) for r in _ONCE_RES):
        return VisionIntent("once", _hint(q))
    # "olha o profit": só vale quando o que veio depois é um programa conhecido.
    m = _LOOK_APP.match(q)
    if m:
        from .apps import resolve

        if resolve(m.group("app")):
            return VisionIntent("once", m.group("app").strip())
    return None


_HINT_STOP = {"tela", "janela", "monitor", "isso", "aqui", "grafico", "comigo", "juntos", "junto", "momento", "agora"}


def _hint(q: str) -> Optional[str]:
    """Se a frase cita um programa ('olha o profit', 'analisa o grafico do profit'), devolve o nome."""
    m = _APP_AFTER.search(re.sub(r"\s+(?:comigo|juntos?|agora|por favor)$", "", q))
    if m:
        words = [w for w in m.group("app").split() if w not in _HINT_STOP]
        if words:
            return " ".join(words)
    return None
