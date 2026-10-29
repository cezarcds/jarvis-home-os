"""Google Agenda (somente leitura)."""
import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List

from ..google_auth import check_google, get_service
from .registry import Param, tool
from .util import TZ, falar_hora, plural, rotulo_dia

_TODOS = Param("todos_calendarios", "bool", False, "Incluir todos os calendários selecionados, não só o principal")


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(TZ)


def _buscar(inicio: datetime, fim: datetime, todos: bool) -> List[Dict[str, Any]]:
    svc = get_service("calendar", "v3")
    ids = ["primary"]
    if todos:
        itens = svc.calendarList().list(minAccessRole="reader").execute().get("items", [])
        ids = [c["id"] for c in itens if c.get("selected") or c.get("primary")] or ["primary"]
    out: List[Dict[str, Any]] = []
    for cid in ids:
        res = svc.events().list(
            calendarId=cid, timeMin=inicio.isoformat(), timeMax=fim.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=50,
        ).execute()
        for ev in res.get("items", []):
            if ev.get("status") == "cancelled":
                continue
            eu = next((a for a in ev.get("attendees", []) if a.get("self")), None)
            if eu and eu.get("responseStatus") == "declined":
                continue
            st, en = ev.get("start", {}), ev.get("end", {})
            if "dateTime" in st:
                s, e = _dt(st["dateTime"]), _dt(en.get("dateTime", st["dateTime"]))
                item = {"dia": s.date().isoformat(), "inicio": s.strftime("%H:%M"), "fim": e.strftime("%H:%M"),
                        "dia_todo": False, "_ord": s.isoformat()}
            else:
                d = max(date.fromisoformat(st["date"]), inicio.date())
                item = {"dia": d.isoformat(), "inicio": None, "fim": None, "dia_todo": True,
                        "_ord": d.isoformat() + "T00:00"}
            item.update(titulo=ev.get("summary") or "(sem título)", local=ev.get("location"),
                        link_reuniao=ev.get("hangoutLink"))
            out.append(item)
    out.sort(key=lambda x: x["_ord"])
    for x in out:
        x.pop("_ord", None)
    return out


def _agrupar(eventos: List[Dict[str, Any]], dias: List[date]) -> List[Dict[str, Any]]:
    grupos = []
    for d in dias:
        iso = d.isoformat()
        grupos.append({"data": iso, "rotulo": rotulo_dia(d), "eventos": [e for e in eventos if e["dia"] == iso]})
    return grupos


def _resumo_llm(grupos) -> str:
    linhas = []
    for g in grupos:
        linhas.append(f"{g['rotulo']}:")
        if not g["eventos"]:
            linhas.append("  (livre)")
        for e in g["eventos"]:
            hora = "dia todo" if e["dia_todo"] else f"{e['inicio']}-{e['fim']}"
            loc = f" ({e['local']})" if e.get("local") else ""
            linhas.append(f"  {hora} {e['titulo']}{loc}")
    return "\n".join(linhas)


def _bloco(titulo: str, grupos, falado: str) -> Dict[str, Any]:
    vazio = all(not g["eventos"] for g in grupos)
    return {"type": "agenda", "title": titulo, "data": {"dias": grupos, "vazio": vazio},
            "falado": falado, "resumo_llm": _resumo_llm(grupos)}


async def _dia(delta: int, todos: bool, titulo: str, quando: str) -> Dict[str, Any]:
    agora = datetime.now(TZ)
    d = agora.date() + timedelta(days=delta)
    ini = datetime.combine(d, time.min, TZ)
    eventos = await asyncio.to_thread(_buscar, ini, ini + timedelta(days=1), todos)
    grupos = _agrupar(eventos, [d])
    n = len(eventos)
    if n == 0:
        falado = f"Sua agenda de {quando} está livre."
    else:
        falado = f"Você tem {n} {plural(n, 'compromisso', 'compromissos')} {quando}."
        horarios = [e for e in eventos if not e["dia_todo"]]
        if delta == 0:
            horarios = [e for e in horarios if e["fim"] > agora.strftime("%H:%M")]
            if horarios:
                falado += f" O próximo é {horarios[0]['titulo']}, às {falar_hora(horarios[0]['inicio'])}."
            elif not horarios:
                falado += " Nada mais pendente por hoje."
        elif horarios:
            falado += f" O primeiro é {horarios[0]['titulo']}, às {falar_hora(horarios[0]['inicio'])}."
    return _bloco(titulo, grupos, falado)


@tool("agenda.hoje", "agenda de hoje", "Compromissos de hoje no Google Agenda", [_TODOS], check=check_google)
async def agenda_hoje(todos_calendarios=False):
    return await _dia(0, bool(todos_calendarios), "Agenda de hoje", "hoje")


@tool("agenda.amanha", "agenda de amanhã", "Compromissos de amanhã no Google Agenda", [_TODOS], check=check_google)
async def agenda_amanha(todos_calendarios=False):
    return await _dia(1, bool(todos_calendarios), "Agenda de amanhã", "amanhã")


@tool(
    "agenda.proximos_dias", "agenda dos próximos dias",
    "Compromissos dos próximos N dias (a partir de hoje) no Google Agenda",
    [Param("dias", "int", 3, "Quantidade de dias", 1, 14), _TODOS],
    check=check_google,
)
async def agenda_proximos(dias=3, todos_calendarios=False):
    agora = datetime.now(TZ)
    hoje = agora.date()
    ini = datetime.combine(hoje, time.min, TZ)
    eventos = await asyncio.to_thread(_buscar, ini, ini + timedelta(days=int(dias)), bool(todos_calendarios))
    grupos = _agrupar(eventos, [hoje + timedelta(days=i) for i in range(int(dias))])
    n = len(eventos)
    falado = (f"Nos próximos {dias} dias você tem {n} {plural(n, 'compromisso', 'compromissos')}."
              if n else f"Nos próximos {dias} dias sua agenda está livre.")
    return _bloco(f"Agenda dos próximos {dias} dias", grupos, falado)
