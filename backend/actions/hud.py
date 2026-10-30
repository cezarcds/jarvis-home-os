"""Abre o HUD numa janela de app (sem barra de endereço), com perfil próprio do navegador."""
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import httpx

from . import winapi
from .apps import jarvis_window

log = logging.getLogger("jarvis.hud")


def dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def dist_available() -> bool:
    return (dist_dir() / "index.html").exists()


def hud_url() -> str:
    explicit = (os.getenv("JARVIS_HUD_URL") or "").strip()
    if explicit:
        return explicit
    if dist_available():  # HUD já compilado: o próprio backend serve, uma porta só
        from connections.config import backend_url

        return backend_url()
    return "http://localhost:5173"  # modo desenvolvimento (npm run dev)


def _candidates() -> List[str]:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    chrome = [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
              rf"{local}\Google\Chrome\Application\chrome.exe"]
    edge = [rf"{pf86}\Microsoft\Edge\Application\msedge.exe", rf"{pf}\Microsoft\Edge\Application\msedge.exe"]
    order = (os.getenv("JARVIS_BROWSER_ORDER") or "chrome,edge").lower().split(",")
    out: List[str] = []
    for name in order:
        out += chrome if name.strip() == "chrome" else edge if name.strip() == "edge" else []
    return out


def find_browser() -> Optional[str]:
    explicit = (os.getenv("JARVIS_BROWSER") or "").strip()
    if explicit and Path(explicit).exists():
        return explicit
    for c in _candidates():
        if c and Path(c).exists():
            return c
    return shutil.which("chrome") or shutil.which("msedge")


def build_command(browser: str, url: str, profile: Path) -> List[str]:
    return [
        browser,
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--autoplay-policy=no-user-gesture-required",  # deixa o Jarvis falar e ouvir sem um clique antes
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,800",
    ]


def _wait_url(url: str, timeout: float = 25.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=2.0).status_code < 500:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def open_hud() -> bool:
    from connections.config import data_dir

    browser = find_browser()
    if not browser:
        log.warning("Não achei Chrome nem Edge. Defina JARVIS_BROWSER com o caminho do executável.")
        return False
    profile = Path(os.getenv("JARVIS_HUD_PROFILE") or data_dir() / "hud-profile")
    cmd = build_command(browser, hud_url(), profile)
    subprocess.Popen(cmd, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    log.info("HUD aberto em modo app: %s", hud_url())
    return True


def open_hud_if_needed() -> bool:
    """Bloqueante (rode em thread). Não abre uma segunda janela se o HUD já está aberto."""
    if winapi.AVAILABLE and jarvis_window(winapi.list_windows()):
        log.info("HUD já está aberto.")
        return False
    if not _wait_url(hud_url()):
        log.warning("O HUD (%s) não respondeu. Rode 'npm run build' no frontend ou 'npm run dev'.", hud_url())
        return False
    return open_hud()
