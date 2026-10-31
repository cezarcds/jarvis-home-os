"""Telemetria real do computador, para o painel SISTEMA do HUD."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1/system")

try:
    import psutil
    psutil.cpu_percent(interval=None)  # a 1ª leitura é sempre 0: a "prepara" para as seguintes serem reais
except ImportError:  # pragma: no cover
    psutil = None


@router.get("/stats")
async def stats():
    if psutil is None:
        raise HTTPException(501, "Instale o psutil: pip install psutil")
    return {"cpu": round(psutil.cpu_percent(interval=None)), "mem": round(psutil.virtual_memory().percent)}
