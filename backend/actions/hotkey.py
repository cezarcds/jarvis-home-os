"""Atalho global de parada (padrão Ctrl+Alt+J, configurável em JARVIS_STOP_HOTKEY).

Usa RegisterHotKey do Windows numa thread própria. Em outros sistemas não faz nada. O módulo
importa em qualquer SO (só toca ctypes.windll quando está no Windows).
"""
import logging
import os
import sys
import threading
from typing import Optional, Tuple

from . import gate

log = logging.getLogger("jarvis.hotkey")

DEFAULT = "ctrl+alt+j"
MOD = {"alt": 0x0001, "ctrl": 0x0002, "control": 0x0002, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0x4A41

_thread: Optional[threading.Thread] = None
_thread_id: Optional[int] = None


def hotkey_text() -> str:
    return (os.getenv("JARVIS_STOP_HOTKEY") or DEFAULT).strip().lower()


def parse(texto: str) -> Tuple[int, int]:
    """'ctrl+alt+j' -> (modificadores, código da tecla virtual). Exige ao menos um modificador
    (uma letra sozinha como atalho global tomaria a tecla do resto do sistema)."""
    partes = [p.strip() for p in texto.lower().split("+") if p.strip()]
    if len(partes) < 2:
        raise ValueError("Use modificador + tecla, por exemplo ctrl+alt+j.")
    *mods, tecla = partes
    flags = 0
    for m in mods:
        if m not in MOD:
            raise ValueError(f"Modificador desconhecido: {m}")
        flags |= MOD[m]
    if len(tecla) == 1 and tecla.isalnum():
        vk = ord(tecla.upper())
    elif tecla.startswith("f") and tecla[1:].isdigit() and 1 <= int(tecla[1:]) <= 24:
        vk = 0x70 + int(tecla[1:]) - 1
    else:
        raise ValueError(f"Tecla não suportada: {tecla}")
    return flags, vk


def _loop(flags: int, vk: int) -> None:
    global _thread_id
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    _thread_id = kernel32.GetCurrentThreadId()
    if not user32.RegisterHotKey(None, HOTKEY_ID, flags | MOD_NOREPEAT, vk):
        log.warning("Não consegui registrar o atalho de parada (%s): outro programa já usa essa combinação.", hotkey_text())
        _thread_id = None
        return
    log.info("Atalho global de parada ativo: %s", hotkey_text())
    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                log.info("Atalho de parada acionado")
                gate.parar("atalho")
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        _thread_id = None


def start() -> bool:
    """Liga o atalho. Devolve False se não for Windows ou se a configuração for inválida."""
    global _thread
    if sys.platform != "win32" or _thread is not None:
        return False
    try:
        flags, vk = parse(hotkey_text())
    except ValueError as exc:
        log.warning("JARVIS_STOP_HOTKEY inválido (%s); atalho de parada desligado.", exc)
        return False
    _thread = threading.Thread(target=_loop, args=(flags, vk), name="jarvis-hotkey", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    global _thread
    if _thread_id and sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.PostThreadMessageW(_thread_id, WM_QUIT, 0, 0)  # type: ignore[attr-defined]
    _thread = None
