"""Processos filhos do Jarvis: rodar sem shell, com timeout, e matar a ÁRVORE inteira.

Os processos vivos ficam registrados aqui para o botão PARAR (gancho do gate) matar mesmo quando a
thread/tarefa que os esperava já foi cancelada.
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import threading
from typing import Dict, List, Optional, Tuple

_vivos: Dict[int, "asyncio.subprocess.Process"] = {}
_trava = threading.Lock()
SAIDA_MAX = 4000

_ENV_BASICO = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "HOME",
               "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
               "LANG", "LC_ALL")


def ambiente_minimo() -> Dict[str, str]:
    """Só o essencial para o programa achar o Python/Node: nenhuma chave de API do Jarvis vaza."""
    return {k: v for k, v in os.environ.items() if k.upper() in _ENV_BASICO}


def _matar_pid(pid: int) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def matar_todos() -> int:
    """Gancho do botão PARAR: mata a árvore de cada processo registrado."""
    with _trava:
        pids = list(_vivos)
    for pid in pids:
        _matar_pid(pid)
    return len(pids)


async def rodar(argv: List[str], cwd: str, timeout_s: float,
                ambiente: Optional[Dict[str, str]] = None) -> Tuple[int, str, bool]:
    """Roda `argv` sem shell. Devolve (código, saída truncada, estourou_o_tempo).
    No timeout ou cancelamento, a árvore de processos inteira é encerrada."""
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, env=ambiente if ambiente is not None else ambiente_minimo(),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **kw)
    with _trava:
        _vivos[proc.pid] = proc
    estourou = False
    try:
        try:
            bruto, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            estourou = True
            _matar_pid(proc.pid)
            bruto, _ = await proc.communicate()
        texto = (bruto or b"").decode("utf-8", errors="replace")
        return proc.returncode if proc.returncode is not None else -1, texto[-SAIDA_MAX:], estourou
    except asyncio.CancelledError:
        _matar_pid(proc.pid)
        raise
    finally:
        with _trava:
            _vivos.pop(proc.pid, None)
        if proc.returncode is None:
            _matar_pid(proc.pid)
