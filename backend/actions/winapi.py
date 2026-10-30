"""Camada fina sobre a API do Windows (ctypes, sem dependências extras).

Em outros sistemas `AVAILABLE` é False e as funções levantam ActionError, para o resto
do código (e os testes) poderem importar este módulo em qualquer lugar.
"""
import ctypes
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

from . import ActionError
from .layout import Monitor, Rect

log = logging.getLogger("jarvis.win")

AVAILABLE = sys.platform == "win32"

# Constantes do Windows
SW_RESTORE = 9
SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0004, 0x0010, 0x0040
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000
DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS = 14, 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MONITORINFOF_PRIMARY = 1
ERROR_ACCESS_DENIED = 5


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process: str      # nome do executável em minúsculas, ex.: "code.exe"
    rect: Rect
    minimized: bool = False


def _require() -> None:
    if not AVAILABLE:
        raise ActionError("Controle de janelas só está disponível no Windows.")


if AVAILABLE:  # pragma: no cover - só roda no Windows
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:
        dwmapi = None

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), MONITORENUMPROC, wintypes.LPARAM]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    _dpi_done = False


def enable_dpi_awareness() -> None:
    """Sem isso o Windows 'mente' sobre as coordenadas em telas com escala > 100%."""
    global _dpi_done
    if not AVAILABLE or _dpi_done:
        return
    _dpi_done = True
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # por monitor
    except Exception:  # noqa: BLE001 - já definido ou sistema antigo
        try:
            user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def _rect(r) -> Rect:
    return Rect(int(r.left), int(r.top), int(r.right), int(r.bottom))


def _process_name(hwnd: int) -> str:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def _is_cloaked(hwnd: int) -> bool:
    if dwmapi is None:
        return False
    val = wintypes.DWORD(0)
    try:
        dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:  # noqa: BLE001
        return False
    return val.value != 0


def list_windows(include_minimized: bool = True) -> List[WindowInfo]:
    """Janelas de programas visíveis, na ordem de empilhamento (a de cima primeiro)."""
    _require()
    out: List[WindowInfo] = []

    def cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.strip()
            if not title or title == "Program Manager":
                return True
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if (ex & WS_EX_TOOLWINDOW) and not (ex & WS_EX_APPWINDOW):
                return True
            if _is_cloaked(hwnd):
                return True
            minimized = bool(user32.IsIconic(hwnd))
            if minimized and not include_minimized:
                return True
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append(WindowInfo(int(hwnd), title, _process_name(hwnd), _rect(r), minimized))
        except Exception:  # noqa: BLE001 - uma janela problemática não derruba a lista
            log.debug("Janela ignorada", exc_info=True)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def monitors() -> List[Monitor]:
    _require()
    found: List[Monitor] = []

    def cb(hmon, _hdc, _rect_ptr, _lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            found.append(
                Monitor(
                    index=len(found),
                    rect=_rect(info.rcMonitor),
                    work=_rect(info.rcWork),
                    primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                )
            )
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return found


def foreground_hwnd() -> Optional[int]:
    _require()
    h = user32.GetForegroundWindow()
    return int(h) if h else None


def window_rect(hwnd: int) -> Optional[Rect]:
    _require()
    r = wintypes.RECT()
    return _rect(r) if user32.GetWindowRect(hwnd, ctypes.byref(r)) else None


def _frame_insets(hwnd: int):
    """O Windows 10/11 desenha bordas invisíveis (~7 px). Sem compensar, as janelas ficam com vãos."""
    if dwmapi is None:
        return (0, 0, 0, 0)
    outer = wintypes.RECT()
    inner = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(outer)):
        return (0, 0, 0, 0)
    ok = dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(inner), ctypes.sizeof(inner)
    )
    if ok != 0:
        return (0, 0, 0, 0)
    return (inner.left - outer.left, inner.top - outer.top, outer.right - inner.right, outer.bottom - inner.bottom)


def place(hwnd: int, target: Rect) -> None:
    """Move e redimensiona a janela para `target` (coordenadas visíveis, já sem as bordas invisíveis)."""
    _require()
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.15)
    for attempt in range(2):  # 2ª passada corrige o tamanho ao cruzar monitores com escalas diferentes
        li, ti, ri, bi = _frame_insets(hwnd)
        x, y = target.left - li, target.top - ti
        w, h = target.width + li + ri, target.height + ti + bi
        ok = user32.SetWindowPos(hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        if not ok:
            err = ctypes.get_last_error()
            if err == ERROR_ACCESS_DENIED:
                raise ActionError(
                    "Esse programa roda como administrador e eu não tenho permissão para mover a janela dele. "
                    "Inicie o Jarvis também como administrador."
                )
            raise ActionError(f"Não consegui mover a janela (erro {err}).")
        time.sleep(0.12)


def bring_to_front(hwnd: int) -> None:
    _require()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    cur = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    try:
        if fg_tid and fg_tid != cur:
            attached = bool(user32.AttachThreadInput(cur, fg_tid, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur, fg_tid, False)
