"""Matemática do layout de janelas (pura, sem Windows): testável em qualquer sistema."""
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def overlap_area(self, other: "Rect") -> int:
        w = min(self.right, other.right) - max(self.left, other.left)
        h = min(self.bottom, other.bottom) - max(self.top, other.top)
        return w * h if w > 0 and h > 0 else 0


@dataclass(frozen=True)
class Monitor:
    index: int
    rect: Rect   # monitor inteiro
    work: Rect   # área útil (sem a barra de tarefas)
    primary: bool = False


@dataclass(frozen=True)
class Plan:
    mode: str               # "split" | "dedicated"
    app_rect: Rect
    jarvis_rect: Rect
    app_monitor: int
    jarvis_monitor: int


def split_work_area(work: Rect, ratio: float) -> "tuple[Rect, Rect]":
    """Programa à esquerda (ratio da largura) e Jarvis à direita (o resto)."""
    cut = work.left + round(work.width * ratio)
    return Rect(work.left, work.top, cut, work.bottom), Rect(cut, work.top, work.right, work.bottom)


def monitor_of(monitors: List[Monitor], rect: Optional[Rect]) -> Optional[Monitor]:
    """Monitor onde `rect` mais aparece (None se rect for None ou não houver monitores)."""
    if rect is None or not monitors:
        return None
    best = max(monitors, key=lambda m: m.rect.overlap_area(rect))
    return best if best.rect.overlap_area(rect) > 0 else None


def _primary(monitors: List[Monitor]) -> Monitor:
    return next((m for m in monitors if m.primary), monitors[0])


def plan(
    monitors: List[Monitor],
    mode: str = "auto",
    ratio: float = 2 / 3,
    jarvis_monitor: Optional[int] = None,
    jarvis_rect: Optional[Rect] = None,
) -> Plan:
    """Decide onde ficam o programa e o Jarvis.

    - 1 monitor (ou mode=split): divide a área útil, programa em `ratio` e Jarvis no resto.
    - 2+ monitores (auto/dedicated): o Jarvis ocupa um monitor inteiro (o escolhido em
      JARVIS_MONITOR, senão o primeiro que não é o principal) e o programa vai ao outro.
    """
    if not monitors:
        raise ValueError("Nenhum monitor encontrado.")
    use_dedicated = mode == "dedicated" or (mode == "auto" and len(monitors) > 1)
    if use_dedicated and len(monitors) > 1:
        by_index = {m.index: m for m in monitors}
        if jarvis_monitor in by_index:
            jm = by_index[jarvis_monitor]
        else:
            jm = next((m for m in monitors if not m.primary), monitors[-1])
        am = _primary(monitors) if _primary(monitors).index != jm.index else next(
            m for m in monitors if m.index != jm.index
        )
        return Plan("dedicated", am.work, jm.work, am.index, jm.index)

    # Dividido: usa o monitor onde o Jarvis já está (se souber), senão o principal.
    home = monitor_of(monitors, jarvis_rect) or _primary(monitors)
    app_r, jarvis_r = split_work_area(home.work, ratio)
    return Plan("split", app_r, jarvis_r, home.index, home.index)
