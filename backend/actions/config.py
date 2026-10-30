"""Configuração das ações. Lida na hora do uso (não no import), como no módulo de conexões."""
import os
import re
from typing import Optional, Pattern


def flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "sim", "yes", "on")


def actions_enabled() -> bool:
    return flag("JARVIS_ACTIONS_ENABLED", True)


def vision_enabled() -> bool:
    return flag("JARVIS_VISION_ENABLED", True)


def voice_enabled() -> bool:
    return flag("JARVIS_VOICE_ENABLED", True)


def open_hud_on_start() -> bool:
    # Desligado por padrão: com `uvicorn --reload` abriria uma janela a cada recarga.
    # O iniciar_jarvis.bat liga isso.
    return flag("JARVIS_OPEN_HUD", False)


def app_ratio() -> float:
    """Fração da largura da tela que o programa ocupa no modo dividido (padrão 2/3)."""
    try:
        v = float(os.getenv("JARVIS_APP_RATIO", "") or 2 / 3)
    except ValueError:
        v = 2 / 3
    return min(0.85, max(0.4, v))


def layout_mode() -> str:
    """auto: 1 monitor divide; 2+ monitores dedica um monitor ao Jarvis. split | dedicated força."""
    v = (os.getenv("JARVIS_LAYOUT_MODE") or "auto").strip().lower()
    return v if v in ("auto", "split", "dedicated") else "auto"


def jarvis_monitor() -> Optional[int]:
    raw = (os.getenv("JARVIS_MONITOR") or "").strip()
    return int(raw) if raw.isdigit() else None


def jarvis_window_regex() -> Pattern[str]:
    """Título da janela do HUD. Ancorado para não pegar 'jarvis-home-os - Visual Studio Code'."""
    raw = os.getenv("JARVIS_WINDOW_TITLE") or r"^JARVIS // HOME OS"
    try:
        return re.compile(raw, re.IGNORECASE)
    except re.error:
        return re.compile(r"^JARVIS // HOME OS", re.IGNORECASE)


# Janelas que o Jarvis nunca captura (nem quando estão por cima da região capturada).
DEFAULT_BLOCKED = (
    r"senha|password|bitwarden|1password|keepass|lastpass|authenticator|"
    r"nubank|ita[uú]|bradesco|santander|banco do brasil|caixa econ|\binter\b|"
    r"mercado ?pago|conta corrente|internet banking"
)


def blocked_window_regex() -> Pattern[str]:
    raw = os.getenv("JARVIS_BLOCKED_WINDOWS") or DEFAULT_BLOCKED
    try:
        return re.compile(raw, re.IGNORECASE)
    except re.error:
        return re.compile(DEFAULT_BLOCKED, re.IGNORECASE)


def vision_follow_up_seconds() -> int:
    try:
        return max(15, int(os.getenv("JARVIS_VISION_FOLLOWUP_S", "90")))
    except ValueError:
        return 90
