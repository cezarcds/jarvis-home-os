"""Google Analytics 4 (somente leitura). Requer GA4_PROPERTY_ID no .env (só o número da propriedade)."""
import asyncio
import os
from datetime import date, timedelta

from ..google_auth import check_google, get_credentials
from .registry import Param, ToolError, tool

_METRICAS = [("sessions", "Sessões"), ("activeUsers", "Usuários ativos"), ("screenPageViews", "Visualizações")]


def _check():
    ok, motivo = check_google()
    if not ok:
        return ok, motivo
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient  # noqa: F401
    except ImportError:
        return False, "Instale google-analytics-data (pip install -r requirements.txt)"
    if not os.getenv("GA4_PROPERTY_ID", "").strip():
        return False, "Defina GA4_PROPERTY_ID no .env"
    return True, ""


def _relatorio(dias: int, propriedade: str):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest

    client = BetaAnalyticsDataClient(credentials=get_credentials())

    def valores(inicio: date, fim: date):
        resp = client.run_report(RunReportRequest(
            property=f"properties/{propriedade}",
            date_ranges=[DateRange(start_date=inicio.isoformat(), end_date=fim.isoformat())],
            metrics=[Metric(name=m) for m, _ in _METRICAS],
        ))
        if not resp.rows:
            return [0.0] * len(_METRICAS)
        return [float(v.value) for v in resp.rows[0].metric_values]

    hoje = date.today()
    fim_atual = hoje - timedelta(days=1)
    ini_atual = fim_atual - timedelta(days=dias - 1)
    fim_ant = ini_atual - timedelta(days=1)
    ini_ant = fim_ant - timedelta(days=dias - 1)
    return valores(ini_atual, fim_atual), valores(ini_ant, fim_ant)


@tool(
    "analytics.resumo", "resumo do Analytics",
    "Sessões, usuários e visualizações dos últimos N dias comparados ao período anterior (Google Analytics 4)",
    [Param("dias", "int", 7, "Janela em dias", 1, 90), Param("propriedade", "str", None, "ID da propriedade GA4 (padrão: GA4_PROPERTY_ID)")],
    timeout=30, check=_check,
)
async def analytics_resumo(dias=7, propriedade=None):
    prop = (propriedade or os.getenv("GA4_PROPERTY_ID", "")).strip()
    if not prop:
        raise ToolError("Defina GA4_PROPERTY_ID no .env")
    atual, anterior = await asyncio.to_thread(_relatorio, int(dias), prop)
    itens, falas = [], []
    for (_, rotulo), a, b in zip(_METRICAS, atual, anterior):
        var = None if b == 0 else round((a - b) / b * 100)
        itens.append({"rotulo": rotulo, "valor": int(a), "anterior": int(b), "variacao_pct": var})
        falas.append(f"{rotulo.lower()}: {int(a)}" + (f", {var:+d}% em relação ao período anterior" if var is not None else ""))
    falado = f"Nos últimos {dias} dias, " + "; ".join(falas) + "."
    return {"type": "metricas", "title": f"Analytics, últimos {dias} dias", "data": {"itens": itens},
            "falado": falado, "resumo_llm": falado}


# ---- consulta genérica (Fase 4, somente leitura) ----------------------------------------------------------------
# Só nomes conhecidos (ou personalizados com prefixo oficial). O que vem do modelo nunca vai direto à API.
METRICAS_OK = {
    "sessions", "activeUsers", "newUsers", "totalUsers", "screenPageViews", "eventCount", "engagedSessions",
    "engagementRate", "bounceRate", "averageSessionDuration", "userEngagementDuration", "conversions",
    "keyEvents", "totalRevenue", "transactions", "screenPageViewsPerSession", "sessionsPerUser",
}
DIMENSOES_OK = {
    "date", "day", "week", "month", "year", "country", "city", "deviceCategory", "browser", "operatingSystem",
    "sessionSource", "sessionMedium", "sessionCampaignName", "sessionDefaultChannelGroup", "pagePath",
    "pageTitle", "landingPage", "eventName", "firstUserSource", "firstUserMedium", "language",
}
PREFIXOS_PERSONALIZADOS = ("customEvent:", "customUser:")
_NOME = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")
MAX_METRICAS, MAX_DIMENSOES, MAX_LINHAS, MAX_DIAS = 8, 4, 100, 365


def _lista(csv: str, ok: set, rotulo: str, singular: str, maximo: int, minimo: int) -> list:
    itens = [x.strip() for x in (csv or "").split(",") if x.strip()]
    if not minimo <= len(itens) <= maximo:
        raise ToolError(f"Informe de {minimo} a {maximo} {rotulo}.")
    for n in itens:
        custom = n.startswith(PREFIXOS_PERSONALIZADOS) and _NOME.match(n.split(":", 1)[1] or "")
        if n not in ok and not custom:
            raise ToolError(f"{singular} não permitida: {n[:40]!r}.")
    if len(set(itens)) != len(itens):
        raise ToolError(f"{rotulo.capitalize()} repetidas.")
    return itens


def validar_consulta(metricas: str, dimensoes: str, dias: int, limite: int, propriedade: str) -> dict:
    if not (propriedade or "").isdigit():
        raise ToolError("A propriedade GA4 precisa ser só o número.")
    return {"metricas": _lista(metricas, METRICAS_OK, "métricas", "Métrica", MAX_METRICAS, 1),
            "dimensoes": _lista(dimensoes, DIMENSOES_OK, "dimensões", "Dimensão", MAX_DIMENSOES, 0),
            "dias": max(1, min(int(dias), MAX_DIAS)), "limite": max(1, min(int(limite), MAX_LINHAS)),
            "propriedade": propriedade}


def _consultar(q: dict) -> list:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

    client = BetaAnalyticsDataClient(credentials=get_credentials())
    resp = client.run_report(RunReportRequest(
        property=f"properties/{q['propriedade']}",
        date_ranges=[DateRange(start_date=f"{q['dias']}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name=d) for d in q["dimensoes"]],
        metrics=[Metric(name=m) for m in q["metricas"]], limit=q["limite"]))
    linhas = []
    for r in resp.rows:
        linha = {d: v.value for d, v in zip(q["dimensoes"], r.dimension_values)}
        linha.update({m: float(v.value) for m, v in zip(q["metricas"], r.metric_values)})
        linhas.append(linha)
    return linhas


@tool(
    "analytics.consultar", "consulta ao Analytics",
    "Consulta GA4 (somente leitura) com métricas e dimensões de uma lista permitida, dos últimos N dias.",
    [Param("metricas", "str", "sessions", "métricas separadas por vírgula (ex.: sessions,activeUsers)"),
     Param("dimensoes", "str", "", "dimensões separadas por vírgula (ex.: country,pagePath)"),
     Param("dias", "int", 7, "janela em dias", 1, MAX_DIAS),
     Param("limite", "int", 10, "máximo de linhas", 1, MAX_LINHAS),
     Param("propriedade", "str", None, "ID da propriedade GA4 (padrão: GA4_PROPERTY_ID)")],
    timeout=30, check=_check, le_dado_externo=True,  # nomes de página/origem podem trazer texto de terceiros
)
async def analytics_consultar(metricas="sessions", dimensoes="", dias=7, limite=10, propriedade=None):
    prop = (propriedade or os.getenv("GA4_PROPERTY_ID", "")).strip()
    q = validar_consulta(metricas, dimensoes, dias, limite, prop)
    linhas = await asyncio.to_thread(_consultar, q)
    falado = f"A consulta do Analytics trouxe {len(linhas)} linhas dos últimos {q['dias']} dias."
    return {"type": "metricas", "title": "Analytics", "data": {"consulta": q, "linhas": linhas},
            "falado": falado, "resumo_llm": falado + "\n" + "\n".join(str(l) for l in linhas[:20])}
