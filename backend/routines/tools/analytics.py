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
