"""Ver a tela: captura (monitor ou janela) -> JPEG em memória -> Gemini.

Nada é salvo em disco. Janelas sensíveis (bancos, gerenciadores de senha) bloqueiam a captura.
"""
import io
import logging
import re
from dataclasses import dataclass
from typing import Optional

from . import ActionError
from .config import blocked_window_regex, jarvis_window_regex, vision_enabled
from .layout import Rect

log = logging.getLogger("jarvis.vision")

MAX_SIDE = 1600
JPEG_QUALITY = 82


@dataclass
class Capture:
    jpeg: bytes
    label: str          # "janela Profit" / "tela principal"
    width: int
    height: int


def _blocked_overlap(wins, region: Rect) -> Optional[str]:
    rx = blocked_window_regex()
    for w in wins:
        if w.minimized:
            continue
        if rx.search(w.title) and w.rect.overlap_area(region) > 0:
            return w.title
    return None


def pick_target(wins, mons, hint: Optional[str], foreground: Optional[int], last_hwnd: Optional[int]):
    """Escolhe o que capturar. Devolve (janela|None, rect, rótulo)."""
    from .apps import match_windows, resolve

    rx_j = jarvis_window_regex()
    others = [w for w in wins if not rx_j.search(w.title) and not w.minimized]

    if hint:
        entry = resolve(hint)
        cands = match_windows(entry, others) if entry else []
        if not cands:  # nome solto: procura no título/processo das janelas abertas
            h = hint.lower()
            cands = [w for w in others if h in w.title.lower() or h in w.process.replace(".exe", "")]
        if cands:
            w = cands[0]
            return w, w.rect, f"janela {entry.falado if entry else hint}"
        if entry:  # programa conhecido, mas sem janela aberta
            raise ActionError(f"Não encontrei uma janela aberta do {entry.falado}.")
        # nome solto que não é programa (ex.: "candles"): ignora e usa o alvo padrão

    for hwnd in (foreground, last_hwnd):
        w = next((x for x in others if x.hwnd == hwnd), None)
        if w:
            return w, w.rect, f"janela {w.title[:40]}"
    if others:  # a de cima na pilha que não é o Jarvis
        w = others[0]
        return w, w.rect, f"janela {w.title[:40]}"
    prim = next((m for m in mons if m.primary), mons[0] if mons else None)
    if prim:
        return None, prim.rect, "tela principal"
    raise ActionError("Não encontrei nada para olhar na tela.")


def grab_region(region: Rect) -> Capture:
    try:
        import mss
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise ActionError("Faltam as bibliotecas de captura. Rode: pip install mss pillow") from exc
    with mss.mss() as sct:
        v = sct.monitors[0]  # área virtual (todos os monitores)
        left, top = max(region.left, v["left"]), max(region.top, v["top"])
        right = min(region.right, v["left"] + v["width"])
        bottom = min(region.bottom, v["top"] + v["height"])
        if right - left < 40 or bottom - top < 40:
            raise ActionError("A área para capturar está fora da tela ou pequena demais.")
        shot = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return Capture(buf.getvalue(), "", img.width, img.height)


def capture(win, hint: Optional[str] = None, last_hwnd: Optional[int] = None) -> Capture:
    """Bloqueante: rode em thread."""
    if not vision_enabled():
        raise ActionError("A visão de tela está desligada nas configurações.")
    enable = getattr(win, "enable_dpi_awareness", None)
    if enable:
        enable()
    wins = win.list_windows()
    mons = win.monitors()
    target, region, label = pick_target(wins, mons, hint, win.foreground_hwnd(), last_hwnd)
    if target is not None and target.minimized:
        raise ActionError("Essa janela está minimizada. Abra ela e eu olho.")
    bad = _blocked_overlap(wins, region)
    if bad:
        raise ActionError(
            "Há uma janela sensível aberta nessa área, então não vou capturar a tela por segurança."
        )
    cap = grab_region(region)
    cap.label = label
    log.info("Captura: %s (%dx%d, %d KB)", label, cap.width, cap.height, len(cap.jpeg) // 1024)
    return cap


VISION_SYSTEM = (
    "Você é JARVIS, um assistente residencial sofisticado, calmo e levemente irônico. Responda sempre em português do "
    "Brasil, em 2 a 5 frases curtas, pois serão faladas em voz alta: sem markdown, listas ou emojis. "
    "Você está vendo uma captura da tela do usuário ({label}). Descreva e analise só o que realmente enxerga. "
    "Se um número ou texto não estiver legível, diga que não dá para ler com certeza em vez de chutar. "
    "Em gráficos de preço (candles, volume, indicadores), comente tendência, estrutura (topos e fundos, suportes e "
    "resistências visíveis), volume e os indicadores que aparecem, como leitura para discutir junto com o usuário, "
    "sem prometer resultado. Se a pergunta não puder ser respondida só com o que está na tela, diga o que falta. "
    "Se a pergunta não for sobre a tela, responda normalmente."
)

_DEFAULT_QUESTION = "Descreva o que você vê na minha tela e comente o que parecer mais relevante."


def question_for(text: str) -> str:
    """Se o pedido foi só 'olha a tela', transforma numa pergunta útil para o modelo."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t if len(t.split()) > 4 else (t + ". " if t else "") + _DEFAULT_QUESTION
