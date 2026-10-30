"""Liga as ações e a visão ao assistente: estado por sessão, execução em thread e respostas faladas."""
import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import llm

from . import ActionError, apps, config, intents, vision, winapi
from .intents import OpenIntent

log = logging.getLogger("jarvis.actions")

win = winapi  # trocável nos testes

SESSION_TTL = 3600


@dataclass
class Session:
    last_hwnd: Optional[int] = None
    vision_mode: str = "off"            # off | on (copiloto: cada pergunta captura a tela de novo)
    vision_hint: Optional[str] = None
    last_image: Optional[bytes] = None  # só em memória; nunca vai para o disco
    last_label: str = ""
    last_vision_at: float = 0.0
    touched: float = field(default_factory=time.time)


_sessions: Dict[str, Session] = {}
_lock = threading.Lock()


def _session(sid: str) -> Session:
    now = time.time()
    with _lock:
        for k in [k for k, v in _sessions.items() if now - v.touched > SESSION_TTL]:
            del _sessions[k]
        s = _sessions.setdefault(sid, Session())
        s.touched = now
        return s


def reset_state() -> None:
    with _lock:
        _sessions.clear()


def vision_active(sid: str) -> bool:
    s = _sessions.get(sid)
    if not s:
        return False
    if s.vision_mode == "on":
        return True
    return bool(s.last_image) and time.time() - s.last_vision_at <= config.vision_follow_up_seconds()


def _vision_payload(s: Session) -> Dict[str, Any]:
    return {"mode": s.vision_mode, "label": s.last_label, "follow_up_seconds": config.vision_follow_up_seconds(),
            "active": vision_active_session(s)}


def vision_active_session(s: Session) -> bool:
    return s.vision_mode == "on" or (bool(s.last_image) and time.time() - s.last_vision_at <= config.vision_follow_up_seconds())


def _resp(kind: str, text: str, s: Optional[Session] = None, acao: Optional[dict] = None,
          provider: Optional[str] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"kind": kind, "text": text, "scene": None, "provider": provider}
    if acao:
        out["acao"] = acao
    if s is not None:
        out["vision"] = _vision_payload(s)
    return out


# ---------- Abrir programas e layout ----------

def _texto_abertura(res: Dict[str, Any]) -> str:
    app = res["app"]
    lay = res.get("layout")
    if not res["found_window"]:
        return f"Abri o {app}, mas não consegui localizar a janela para organizar a tela."
    base = f"O {app} já estava aberto" if res["reused"] else f"Abri o {app}"
    if not lay:
        return base + "."
    if str(lay).endswith("sem-jarvis"):
        return base + ", mas não achei a minha janela para dividir a tela. Abra o Jarvis pelo iniciar_jarvis.bat."
    if lay == "dedicated":
        return base + " no monitor principal e fiquei no outro."
    return base + " e organizei a tela."


async def _do_open(oi: OpenIntent, sid: str) -> Optional[Dict[str, Any]]:
    s = _session(sid)
    entry = await asyncio.to_thread(apps.resolve, oi.app)
    if not entry:
        if oi.app_words <= 3:
            return _resp("acao", f"Não encontrei {oi.app} entre os seus programas. Se ele tiver atalho no Menu Iniciar, "
                                 "diga o nome como aparece lá, ou cadastre no arquivo apps.json.")
        return None  # frase longa: provavelmente não era um pedido de abrir programa
    if not win.AVAILABLE:
        return _resp("acao", "Abrir programas só funciona no Windows.")
    try:
        res = await asyncio.to_thread(apps.open_app, entry, win, oi.organize)
    except ActionError as exc:
        return _resp("acao", str(exc))
    if res.get("hwnd"):
        s.last_hwnd = res["hwnd"]
    log.info("Ação: abrir %s -> %s", entry.id, res)
    return _resp("acao", _texto_abertura(res), s, acao={"tipo": "abrir", **{k: v for k, v in res.items() if k != "hwnd"}})


async def _do_layout(kind: str, sid: str) -> Dict[str, Any]:
    s = _session(sid)
    if not win.AVAILABLE:
        return _resp("acao", "Organizar janelas só funciona no Windows.")
    try:
        if kind == "jarvis_full":
            await asyncio.to_thread(apps.restore_jarvis, win)
            return _resp("acao", "Pronto, a tela é toda minha de novo.", s, acao={"tipo": "restaurar_jarvis"})

        def _arrange() -> str:
            enable = getattr(win, "enable_dpi_awareness", None)
            if enable:
                enable()
            from .config import jarvis_window_regex

            rx = jarvis_window_regex()
            wins = [w for w in win.list_windows(include_minimized=False) if not rx.search(w.title)]
            fg = win.foreground_hwnd()
            target = next((w for w in wins if w.hwnd == fg), None) or next(
                (w for w in wins if w.hwnd == s.last_hwnd), None) or (wins[0] if wins else None)
            if not target:
                raise ActionError("Não encontrei uma janela para organizar.")
            s.last_hwnd = target.hwnd
            return apps.apply_layout(target.hwnd, win)

        await asyncio.to_thread(_arrange)
        return _resp("acao", "Tela organizada.", s, acao={"tipo": "organizar"})
    except ActionError as exc:
        return _resp("acao", str(exc), s)


# ---------- Visão ----------

async def _capture(s: Session, hint: Optional[str]) -> vision.Capture:
    if not win.AVAILABLE:
        raise ActionError("A visão de tela só funciona no Windows.")
    cap = await asyncio.to_thread(vision.capture, win, hint, s.last_hwnd)
    s.last_image, s.last_label, s.last_vision_at = cap.jpeg, cap.label, time.time()
    return cap


async def _describe(s: Session, text: str, history: List[Dict[str, str]], jpeg: bytes, label: str,
                    default_question: bool) -> Dict[str, Any]:
    msgs = [{"role": m["role"], "content": m["content"]} for m in history if m.get("role") in ("user", "assistant")]
    q = vision.question_for(text) if default_question else text
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] = q
    else:
        msgs.append({"role": "user", "content": q})
    try:
        reply, provider = await llm.complete(
            msgs, system=vision.VISION_SYSTEM.format(label=label), max_tokens=600, temperature=0.4,
            timeout=35, images=[jpeg],
        )
    except llm.LLMError as exc:
        log.warning("Análise de imagem falhou: %s", str(exc)[:300])
        return _resp("visao", "Capturei a tela, mas não consegui analisar a imagem agora.", s)
    s.last_vision_at = time.time()
    return _resp("visao", reply, s, provider=provider)


async def _do_vision(vi: intents.VisionIntent, text: str, sid: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
    s = _session(sid)
    if not config.vision_enabled():
        return _resp("visao", "A visão de tela está desligada nas configurações.", s)
    if vi.kind == "off":
        s.vision_mode, s.vision_hint, s.last_image, s.last_vision_at = "off", None, None, 0.0
        return _resp("visao", "Certo, parei de olhar a sua tela.", s)
    try:
        cap = await _capture(s, vi.target_hint)
    except ActionError as exc:
        return _resp("visao", str(exc), s)
    if vi.kind == "on":
        s.vision_mode, s.vision_hint = "on", vi.target_hint
        return _resp("visao", f"Modo análise ligado. Estou olhando a {cap.label}; pergunte quando quiser.", s)
    return await _describe(s, text, history, cap.jpeg, cap.label, default_question=True)


async def follow_up_vision(text: str, sid: str, history: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Pergunta comum durante o modo análise (ou logo depois de olhar): responde com a tela junto."""
    if not config.vision_enabled() or not vision_active(sid):
        return None
    s = _session(sid)
    if s.vision_mode == "on":
        try:
            cap = await _capture(s, s.vision_hint)
            return await _describe(s, text, history, cap.jpeg, cap.label, default_question=False)
        except ActionError as exc:
            return _resp("visao", str(exc), s)
    if s.last_image:
        return await _describe(s, text, history, s.last_image, s.last_label, default_question=False)
    return None


# ---------- Entrada principal ----------

async def try_handle(text: str, sid: str, history: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Devolve a resposta se o pedido era uma ação/visão; None para seguir o fluxo normal."""
    if config.actions_enabled():
        oi = intents.parse_open(text)
        if oi:
            return await _do_open(oi, sid)
        lay = intents.parse_layout(text)
        if lay:
            return await _do_layout(lay, sid)
    vi = intents.parse_vision(text)
    if vi:
        return await _do_vision(vi, text, sid, history)
    return None


async def run_tool(name: str, params: Dict[str, Any], sid: str) -> Dict[str, Any]:
    """Ferramenta de ação escolhida pelo LLM (roteamento por significado)."""
    if not config.actions_enabled():
        return _resp("acao", "As ações no computador estão desligadas nas configurações.")
    if name == "app.abrir":
        app = str((params or {}).get("app") or "").strip()
        if not app:
            return _resp("acao", "Qual programa você quer abrir?")
        organizar = (params or {}).get("organizar", True)
        res = await _do_open(OpenIntent(app=app, organize=bool(organizar), app_words=len(app.split())), sid)
        return res or _resp("acao", f"Não encontrei {app} entre os seus programas.")
    if name == "tela.organizar":
        return await _do_layout("arrange", sid)
    if name == "tela.restaurar_jarvis":
        return await _do_layout("jarvis_full", sid)
    return _resp("acao", "Não sei executar essa ação.")
