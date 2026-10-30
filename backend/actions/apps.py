"""Catálogo de programas que o Jarvis pode abrir.

Só abre o que está aqui (lista própria em ~/.jarvis/apps.json + padrões abaixo) ou o que
tem atalho no Menu Iniciar. Nunca executa comandos soltos vindos da fala ou do LLM.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from routines.textutil import slugify

from . import ActionError
from .config import app_ratio, jarvis_monitor, jarvis_window_regex, layout_mode
from .layout import monitor_of, plan as plan_layout

log = logging.getLogger("jarvis.apps")


def _norm(s: str) -> str:
    """Normalização simples para nomes de programas (sem cortar 'jarvis' das pontas)."""
    import unicodedata

    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class AppEntry:
    id: str
    nomes: List[str]                                   # como você chama o programa em voz alta
    comandos: List[str] = field(default_factory=list)  # executáveis candidatos (aceita %VARIAVEIS%)
    atalho: Optional[str] = None                       # trecho do nome do atalho no Menu Iniciar
    uri: Optional[str] = None                          # ex.: "spotify:" ou "https://..."
    titulo_regex: Optional[str] = None                 # para achar a janela depois de aberto
    processos: List[str] = field(default_factory=list)  # ex.: ["code.exe"]
    layout: bool = True                                # organizar a tela ao abrir
    rotulo: Optional[str] = None                       # como o Jarvis fala o nome

    @property
    def falado(self) -> str:
        return self.rotulo or self.nomes[0]


# Padrões. Para o Profit, o caminho do executável varia por instalação; o atalho do Menu
# Iniciar resolve sem precisar saber. Ajuste/adicione tudo em ~/.jarvis/apps.json.
DEFAULTS: List[dict] = [
    {"id": "vscode", "rotulo": "VS Code",
     "nomes": ["vs code", "vscode", "visual studio code", "codigo", "code"],
     "comandos": [r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                  r"%ProgramFiles%\Microsoft VS Code\Code.exe", "code"],
     "titulo_regex": "Visual Studio Code", "processos": ["code.exe"]},
    {"id": "profit", "rotulo": "Profit",
     "nomes": ["profit", "profit pro", "profitpro", "profit chart", "profitchart"],
     "atalho": "profit", "titulo_regex": "Profit"},
    {"id": "chrome", "rotulo": "Chrome", "nomes": ["chrome", "google chrome", "navegador"],
     "comandos": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                  r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                  r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
     "titulo_regex": r"Google Chrome$", "processos": ["chrome.exe"]},
    {"id": "edge", "rotulo": "Edge", "nomes": ["edge", "microsoft edge"],
     "comandos": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                  r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"],
     "titulo_regex": r"Microsoft.? Edge$", "processos": ["msedge.exe"]},
    {"id": "explorer", "rotulo": "Explorador de Arquivos",
     "nomes": ["explorador", "explorador de arquivos", "arquivos", "pastas"],
     "comandos": ["explorer.exe"], "processos": ["explorer.exe"]},
    {"id": "notepad", "rotulo": "Bloco de Notas", "nomes": ["bloco de notas", "notepad"],
     "comandos": ["notepad.exe"], "processos": ["notepad.exe"]},
    {"id": "calculadora", "rotulo": "Calculadora", "nomes": ["calculadora", "calc"],
     "comandos": ["calc.exe"], "titulo_regex": "Calculadora|Calculator"},
    {"id": "terminal", "rotulo": "Terminal", "nomes": ["terminal", "powershell", "prompt de comando"],
     "comandos": ["wt.exe", "powershell.exe"], "titulo_regex": "PowerShell|Terminal|Prompt"},
]


def _user_file() -> Path:
    from connections.config import data_dir

    return data_dir() / "apps.json"


def _from_dict(d: dict) -> AppEntry:
    nomes = [str(n) for n in d.get("nomes", []) if str(n).strip()]
    if not nomes:
        raise ValueError("app sem 'nomes'")
    return AppEntry(
        id=slugify(d.get("id") or nomes[0]), nomes=nomes,
        comandos=[str(c) for c in d.get("comandos", [])],
        atalho=d.get("atalho"), uri=d.get("uri"), titulo_regex=d.get("titulo_regex"),
        processos=[str(p).lower() for p in d.get("processos", [])],
        layout=bool(d.get("layout", True)), rotulo=d.get("rotulo"),
    )


def load_catalog() -> List[AppEntry]:
    """Padrões + o que você definiu em apps.json (mesmo 'id' substitui o padrão)."""
    entries: Dict[str, AppEntry] = {}
    for d in DEFAULTS:
        e = _from_dict(d)
        entries[e.id] = e
    try:
        f = _user_file()
        if f.exists():
            for d in json.loads(f.read_text(encoding="utf-8")):
                try:
                    e = _from_dict(d)
                    entries[e.id] = e
                except (ValueError, TypeError) as exc:
                    log.warning("apps.json: entrada ignorada (%s)", exc)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Não consegui ler apps.json: %s", exc)
    return list(entries.values())


# ---------- Menu Iniciar ----------

_start_cache: Tuple[float, Dict[str, str]] = (0.0, {})


def start_menu_index() -> Dict[str, str]:
    """{nome normalizado do atalho: caminho do .lnk}. Cache de 5 min."""
    global _start_cache
    if sys.platform != "win32":
        return {}
    if time.time() - _start_cache[0] < 300 and _start_cache[1]:
        return _start_cache[1]
    roots = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    idx: Dict[str, str] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*.lnk"):
            n = _norm(p.stem)
            if n and "uninstall" not in n and "desinstal" not in n:
                idx.setdefault(n, str(p))
    _start_cache = (time.time(), idx)
    return idx


def _find_lnk(fragment: str) -> Optional[str]:
    frag = _norm(fragment)
    idx = start_menu_index()
    exact = [p for n, p in idx.items() if n == frag]
    if exact:
        return exact[0]
    contains = sorted(((n, p) for n, p in idx.items() if frag in n.split() or n.startswith(frag)),
                      key=lambda x: len(x[0]))
    return contains[0][1] if contains else None


# ---------- Resolução do que foi dito ----------

def _score(phrase: str, alias: str) -> float:
    if phrase == alias:
        return 1.0
    if len(alias) >= 3 and re.search(rf"\b{re.escape(alias)}\b", phrase):
        return 0.93
    if len(phrase) >= 4 and re.search(rf"\b{re.escape(phrase)}\b", alias):
        return 0.9
    return SequenceMatcher(None, phrase, alias).ratio()


def resolve(phrase: str, catalog: Optional[List[AppEntry]] = None) -> Optional[AppEntry]:
    """Descobre qual programa o usuário quis dizer (catálogo primeiro, Menu Iniciar depois)."""
    p = _norm(phrase)
    if not p:
        return None
    catalog = catalog if catalog is not None else load_catalog()
    best, best_score = None, 0.0
    for e in catalog:
        for nome in e.nomes:
            s = _score(p, _norm(nome))
            if s > best_score:
                best, best_score = e, s
    if best and best_score >= 0.82:
        return best
    # Qualquer programa com atalho no Menu Iniciar (Spotify, WhatsApp, etc.)
    idx = start_menu_index()
    cand, cscore = None, 0.0
    for n, path in idx.items():
        s = _score(p, n)
        if s > cscore:
            cand, cscore = (n, path), s
    if cand and cscore >= 0.88:
        n, path = cand
        return AppEntry(id=slugify(n), nomes=[n], atalho=n, rotulo=Path(path).stem, layout=True)
    return None


# ---------- Janelas e abertura ----------

def jarvis_window(wins) -> Optional[object]:
    rx = jarvis_window_regex()
    return next((w for w in wins if rx.search(w.title)), None)


def match_windows(entry: AppEntry, wins) -> list:
    """Janelas (da de cima para a de baixo) que pertencem a esse programa, exceto o HUD."""
    rx_j = jarvis_window_regex()
    rx = re.compile(entry.titulo_regex, re.IGNORECASE) if entry.titulo_regex else None
    procs = set(entry.processos)
    out = []
    for w in wins:
        if rx_j.search(w.title):
            continue
        if (rx and rx.search(w.title)) or (procs and w.process in procs):
            out.append(w)
    return out


def _expand(cmd: str) -> str:
    return os.path.expandvars(cmd)


def _spawn(cmd: str) -> None:
    path = _expand(cmd)
    resolved = path if os.path.isabs(path) and os.path.exists(path) else shutil.which(path)
    if not resolved:
        raise FileNotFoundError(cmd)
    if resolved.lower().endswith(".lnk"):
        os.startfile(resolved)  # type: ignore[attr-defined]
        return
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([resolved], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch(entry: AppEntry) -> None:
    """Dispara o programa. Levanta ActionError se não achar nada para executar."""
    if sys.platform != "win32":
        raise ActionError("Abrir programas só está disponível no Windows.")
    if entry.uri:
        os.startfile(entry.uri)  # type: ignore[attr-defined]
        return
    for cmd in entry.comandos:
        try:
            _spawn(cmd)
            return
        except (FileNotFoundError, OSError):
            continue
    if entry.atalho:
        lnk = entry.atalho if entry.atalho.lower().endswith(".lnk") else _find_lnk(entry.atalho)
        if lnk:
            os.startfile(lnk)  # type: ignore[attr-defined]
            return
    raise ActionError(
        f"Não encontrei o {entry.falado} instalado. Você pode informar o caminho dele no arquivo apps.json."
    )


def wait_new_window(entry: AppEntry, before_hwnds: set, win, timeout: float = 12.0):
    """Espera a janela do programa aparecer. Devolve a WindowInfo ou None."""
    deadline = time.time() + timeout
    rx_j = jarvis_window_regex()
    while time.time() < deadline:
        wins = win.list_windows(include_minimized=False)
        mine = [w for w in match_windows(entry, wins) if w.hwnd not in before_hwnds]
        if not mine and not entry.titulo_regex and not entry.processos:
            # Programa descoberto no Menu Iniciar: qualquer janela nova (menos o HUD) é a dele.
            mine = [w for w in wins if w.hwnd not in before_hwnds and not rx_j.search(w.title)]
        if mine:
            time.sleep(0.6)  # deixa a janela terminar de montar antes de mexer nela
            return mine[0]
        time.sleep(0.3)
    return None


def apply_layout(app_hwnd: int, win) -> str:
    """Programa em 2/3 e Jarvis em 1/3 (ou, com vários monitores, cada um no seu). Devolve o modo usado."""
    mons = win.monitors()
    wins = win.list_windows()
    jw = jarvis_window(wins)
    p = plan_layout(mons, layout_mode(), app_ratio(), jarvis_monitor(), jw.rect if jw else None)
    win.place(app_hwnd, p.app_rect)
    if jw:
        win.place(jw.hwnd, p.jarvis_rect)
    win.bring_to_front(app_hwnd)
    return p.mode if jw else p.mode + "-sem-jarvis"


def open_app(entry: AppEntry, win, organize: bool = True) -> Dict[str, object]:
    """Abre (ou traz para frente, se já está aberto) e organiza a tela. Bloqueante: rode em thread."""
    enable = getattr(win, "enable_dpi_awareness", None)
    if enable:
        enable()
    existing = match_windows(entry, win.list_windows())
    reused = bool(existing)
    if existing:
        target = existing[0]
    else:
        before = {w.hwnd for w in win.list_windows()}
        launch(entry)
        target = wait_new_window(entry, before, win)
    result: Dict[str, object] = {"app": entry.falado, "reused": reused, "found_window": target is not None,
                                 "layout": None, "hwnd": target.hwnd if target is not None else None}
    if target is None:
        return result
    if organize and entry.layout:
        result["layout"] = apply_layout(target.hwnd, win)
    else:
        win.bring_to_front(target.hwnd)
    return result


def restore_jarvis(win) -> None:
    """O HUD volta a ocupar a área útil inteira do monitor onde está."""
    enable = getattr(win, "enable_dpi_awareness", None)
    if enable:
        enable()
    jw = jarvis_window(win.list_windows())
    if not jw:
        raise ActionError("Não achei a minha janela. Abra o Jarvis pelo iniciar_jarvis.bat.")
    mons = win.monitors()
    m = monitor_of(mons, jw.rect) or next((x for x in mons if x.primary), mons[0])
    win.place(jw.hwnd, m.work)
    win.bring_to_front(jw.hwnd)
