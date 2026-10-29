import os
from datetime import date
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("JARVIS_TZ", "America/Sao_Paulo"))

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def rotulo_dia(d: date) -> str:
    return f"{DIAS[d.weekday()].capitalize()}, {d.day} de {MESES[d.month - 1]}"


def falar_hora(hhmm: str) -> str:
    """'09:30' -> '9h30'; '14:00' -> '14h'."""
    h, m = hhmm.split(":")
    return f"{int(h)}h" if m == "00" else f"{int(h)}h{m}"


def plural(n: int, um: str, varios: str) -> str:
    return um if n == 1 else varios
