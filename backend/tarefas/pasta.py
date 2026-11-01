"""Importa tarefas escritas à mão: arquivos .json em ~/.jarvis/tarefas/ (fora do repositório).

Cada arquivo vira (ou atualiza) uma tarefa. Arquivo inválido NÃO derruba nada: o erro volta na lista
de resultados. A situação 'ativa' que você escolheu no HUD é preservada na reimportação.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from connections.config import data_dir

from . import store
from .models import carregar


def pasta() -> Path:
    p = data_dir() / "tarefas"
    p.mkdir(parents=True, exist_ok=True)
    return p


def importar(agora: Optional[float] = None) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    for arq in sorted(pasta().glob("*.json")):
        try:
            tarefa = carregar(json.loads(arq.read_text(encoding="utf-8")))
            atual = store.obter(tarefa.id)
            if atual is not None:
                tarefa.ativa = atual.ativa
            store.salvar(tarefa, agora)
            resultados.append({"arquivo": arq.name, "tarefa": tarefa.id, "ok": True})
        except Exception as exc:  # noqa: BLE001 - validação, JSON ruim, schema futuro...
            resultados.append({"arquivo": arq.name, "tarefa": None, "ok": False, "erro": str(exc)[:400]})
    return resultados
