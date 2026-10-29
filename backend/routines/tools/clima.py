"""Clima atual e previsão do dia (Open-Meteo, sem chave)."""
import os

import httpx

from .registry import Param, ToolError, tool

_WMO = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 80: "pancadas de chuva", 81: "pancadas de chuva",
    82: "pancadas fortes de chuva", 95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas com granizo",
}


@tool(
    "clima.agora", "clima",
    "Temperatura atual, máxima/mínima e chance de chuva de hoje no local da casa",
    [Param("lat", "float", None, "Latitude (padrão: JARVIS_LAT ou São Paulo)"),
     Param("lon", "float", None, "Longitude (padrão: JARVIS_LON ou São Paulo)")],
    timeout=12,
)
async def clima_agora(lat=None, lon=None):
    lat = lat if lat is not None else float(os.getenv("JARVIS_LAT", "-23.55"))
    lon = lon if lon is not None else float(os.getenv("JARVIS_LON", "-46.63"))
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=1"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
    if r.is_error:
        raise ToolError("Serviço de clima indisponível")
    j = r.json()
    c, d = j["current"], j["daily"]
    desc = _WMO.get(c.get("weather_code"), "tempo variável")
    data = {
        "temperatura": round(c["temperature_2m"]), "sensacao": round(c["apparent_temperature"]),
        "umidade": c["relative_humidity_2m"], "vento": round(c["wind_speed_10m"]), "descricao": desc,
        "maxima": round(d["temperature_2m_max"][0]), "minima": round(d["temperature_2m_min"][0]),
        "chuva_prob": d["precipitation_probability_max"][0],
    }
    falado = (f"Agora faz {data['temperatura']} graus, {desc}. Máxima de {data['maxima']} e mínima de "
              f"{data['minima']}, com {data['chuva_prob']}% de chance de chuva.")
    resumo = (f"{data['temperatura']}°C, {desc}, máx {data['maxima']}°C, mín {data['minima']}°C, "
              f"chuva {data['chuva_prob']}%")
    return {"type": "clima", "title": "Clima", "data": data, "falado": falado, "resumo_llm": resumo}
