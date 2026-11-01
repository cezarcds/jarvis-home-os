"""Cron de 5 campos (minuto hora dia mês dia-da-semana), com fuso, sem dependência nova.

Suporta `*`, valores, intervalos (`1-5`), passos (`*/15`, `10-30/5`) e listas (`1,15`).
Dia da semana: 0 ou 7 = domingo. Como no cron clássico, se dia-do-mês E dia-da-semana estão
restritos, vale qualquer um dos dois.

As ocorrências são calculadas no relógio de parede do fuso. Horário que não existe (salto do
horário de verão) é pulado; horário repetido vale uma vez só (a primeira).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import FrozenSet, List, Optional, Tuple
from zoneinfo import ZoneInfo

_LIMITES = [(0, 59, "minuto"), (0, 23, "hora"), (1, 31, "dia do mês"), (1, 12, "mês"), (0, 7, "dia da semana")]
MAX_DIAS = 366 * 5  # alcance máximo da busca (cobre 29 de fevereiro)


@dataclass(frozen=True)
class Cron:
    minutos: FrozenSet[int]
    horas: FrozenSet[int]
    dias: FrozenSet[int]
    meses: FrozenSet[int]
    semana: FrozenSet[int]      # 0 = domingo ... 6 = sábado
    dias_livre: bool            # campo do dia do mês era "*"
    semana_livre: bool          # campo do dia da semana era "*"

    def dia_casa(self, d: date) -> bool:
        if d.month not in self.meses:
            return False
        dow = (d.weekday() + 1) % 7  # segunda=0 -> domingo=0
        por_dia, por_semana = d.day in self.dias, dow in self.semana
        if self.dias_livre and self.semana_livre:
            return True
        if self.dias_livre:
            return por_semana
        if self.semana_livre:
            return por_dia
        return por_dia or por_semana


def _campo(texto: str, lo: int, hi: int, nome: str) -> Tuple[FrozenSet[int], bool]:
    valores: set = set()
    for parte in texto.split(","):
        if not parte:
            raise ValueError(f"cron: campo de {nome} vazio")
        base, _, passo_txt = parte.partition("/")
        if passo_txt:
            if not passo_txt.isdigit() or int(passo_txt) < 1:
                raise ValueError(f"cron: passo inválido em {nome}: {parte}")
            passo = int(passo_txt)
        else:
            passo = 1
        if base == "*":
            ini, fim = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            if not (a.isdigit() and b.isdigit()):
                raise ValueError(f"cron: intervalo inválido em {nome}: {parte}")
            ini, fim = int(a), int(b)
        elif base.isdigit():
            ini = int(base)
            fim = hi if passo_txt else ini
        else:
            raise ValueError(f"cron: valor inválido em {nome}: {parte}")
        if ini < lo or fim > hi or ini > fim:
            raise ValueError(f"cron: {nome} fora do intervalo {lo}-{hi}: {parte}")
        valores.update(range(ini, fim + 1, passo))
    return frozenset(valores), texto == "*"


def parse(expr: str) -> Cron:
    campos = (expr or "").split()
    if len(campos) != 5:
        raise ValueError("cron: use 5 campos (minuto hora dia mês dia-da-semana), ex.: 0 9 * * *")
    parsed = [_campo(c, lo, hi, nome) for c, (lo, hi, nome) in zip(campos, _LIMITES)]
    semana = frozenset(0 if v == 7 else v for v in parsed[4][0])
    return Cron(parsed[0][0], parsed[1][0], parsed[2][0], parsed[3][0], semana, parsed[2][1], parsed[4][1])


def _existe(naive: datetime, tz: ZoneInfo) -> Optional[datetime]:
    """O horário de parede existe neste fuso? (None se cair no 'buraco' do horário de verão)."""
    aware = naive.replace(tzinfo=tz, fold=0)
    volta = aware.astimezone(timezone.utc).astimezone(tz)
    return aware if volta.replace(tzinfo=None) == naive else None


def _horarios(c: Cron) -> List[time]:
    return [time(h, m) for h in sorted(c.horas) for m in sorted(c.minutos)]


def proxima(expr: str, depois_de: datetime, tz: ZoneInfo) -> Optional[datetime]:
    """Primeira ocorrência ESTRITAMENTE depois de `depois_de`."""
    c = parse(expr)
    ref = depois_de.astimezone(tz)
    d = ref.date()
    horarios = _horarios(c)
    for i in range(MAX_DIAS):
        dia = d + timedelta(days=i)
        if not c.dia_casa(dia):
            continue
        for h in horarios:
            cand = _existe(datetime.combine(dia, h), tz)
            if cand and cand > ref:
                return cand
    return None


def anterior(expr: str, ate: datetime, tz: ZoneInfo) -> Optional[datetime]:
    """Última ocorrência menor ou igual a `ate`."""
    c = parse(expr)
    ref = ate.astimezone(tz)
    d = ref.date()
    horarios = list(reversed(_horarios(c)))
    for i in range(MAX_DIAS):
        dia = d - timedelta(days=i)
        if not c.dia_casa(dia):
            continue
        for h in horarios:
            cand = _existe(datetime.combine(dia, h), tz)
            if cand and cand <= ref:
                return cand
    return None


def chave_slot(slot: datetime) -> str:
    """Identificador estável de uma rodada: horário de parede local + deslocamento (ex.: 2026-10-31T09:00-03:00)."""
    return slot.strftime("%Y-%m-%dT%H:%M%z")
