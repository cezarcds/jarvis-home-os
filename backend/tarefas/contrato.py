"""Contrato em execução: o objeto que o gate consulta antes de cada chamada.

Uma violação devolve uma mensagem em português e o gate levanta ForaDoContrato. Nada aqui executa
ferramenta; só decide. Convenção de nomes de parâmetros (as ferramentas das Fases 3 e 4 devem segui-la,
senão o contrato não enxerga o que elas tocam):

    pasta, pastas, arquivo, arquivos, caminho, destino  -> precisam estar DENTRO de escopo.pastas
    url, dominio, site                                  -> o domínio precisa estar em escopo.dominios
    conta, canal                                        -> precisa estar em escopo.contas
    visibilidade                                        -> precisa ser igual a limites.visibilidade (se definida)
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from . import store
from .models import Tarefa

PARAMS_PASTA = ("pasta", "pastas", "arquivo", "arquivos", "caminho", "destino")
PARAMS_DOMINIO = ("url", "dominio", "site")
PARAMS_CONTA = ("conta", "canal")


def _valores(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [x for item in v for x in _valores(item)]
    return [v]


def dentro_de(caminho: str, pastas: Iterable[str]) -> bool:
    """`caminho` resolvido (sem '..', sem atalhos) está dentro de alguma das `pastas`? Caminho
    relativo conta a partir da primeira pasta do escopo."""
    pastas = [str(p) for p in pastas]
    if not pastas:
        return False
    base = Path(pastas[0])
    p = Path(caminho)
    alvo = os.path.normcase(os.path.realpath(p if p.is_absolute() else base / p))
    for raiz in pastas:
        r = os.path.normcase(os.path.realpath(raiz))
        if alvo == r or alvo.startswith(r.rstrip(os.sep) + os.sep):
            return True
    return False


def dominio_ok(valor: str, permitidos: Iterable[str]) -> bool:
    host = (urlparse(valor if "://" in valor else f"//{valor}").hostname or "").lower().rstrip(".")
    if not host:
        return False
    return any(host == d.lower().lstrip(".") or host.endswith("." + d.lower().lstrip(".")) for d in permitidos)


class ContratoAtivo:
    """Protocolo esperado pelo gate: `aprovado` e `checar(nome, params, nivel, simulacao)`."""

    def __init__(self, tarefa: Tarefa, *, relogio: Callable[[], float] = time.time):
        self.tarefa = tarefa
        self.c = tarefa.contrato
        self.aprovado = tarefa.contrato.aprovado
        self._relogio = relogio
        self._inicio = relogio()
        self.passos = 0
        tz = tarefa.agenda.fuso if tarefa.agenda else "America/Sao_Paulo"
        self._tz = ZoneInfo(tz)

    def _agora(self) -> datetime:
        return datetime.fromtimestamp(self._relogio(), self._tz)

    def na_janela(self, agora: Optional[datetime] = None) -> bool:
        return self._na_janela(agora or self._agora())

    def _na_janela(self, agora: datetime) -> bool:
        j = self.c.limites.janela_horario
        if not j:
            return True
        hhmm = agora.strftime("%H:%M")
        if j.inicio <= j.fim:
            return j.inicio <= hhmm <= j.fim
        return hhmm >= j.inicio or hhmm <= j.fim  # janela que atravessa a meia-noite

    def checar(self, nome: str, params: dict, nivel: int, simulacao: bool = False) -> Optional[str]:
        lim, esc = self.c.limites, self.c.escopo

        if nome not in esc.ferramentas:
            return f"«{nome}» não está entre as ferramentas permitidas pelo contrato."
        if self._relogio() - self._inicio > lim.timeout_min * 60:
            return f"O tempo total da tarefa ({lim.timeout_min} min) acabou."
        agora = self._agora()
        if not self._na_janela(agora):
            j = lim.janela_horario
            return f"Fora da janela de horário do contrato ({j.inicio} a {j.fim})."
        if self.passos >= lim.max_passos:
            return f"O limite de {lim.max_passos} chamadas por execução foi atingido."

        for chave, valor in params.items():
            for v in _valores(valor):
                s = str(v)
                if chave in PARAMS_PASTA and not dentro_de(s, esc.pastas):
                    return f"O caminho «{s}» está fora das pastas permitidas pelo contrato."
                if chave in PARAMS_DOMINIO and not dominio_ok(s, esc.dominios):
                    return f"O domínio de «{s}» não está entre os permitidos pelo contrato."
                if chave in PARAMS_CONTA and s not in esc.contas:
                    return f"A conta «{s}» não está entre as permitidas pelo contrato."
                if chave == "visibilidade" and lim.visibilidade and s != lim.visibilidade:
                    return f"O contrato só permite visibilidade «{lim.visibilidade}», não «{s}»."

        teto = lim.por_dia.get(nome)
        if teto is not None:
            dia = agora.strftime("%Y-%m-%d")
            if simulacao:
                if store.uso_do_dia(self.tarefa.id, nome, dia) >= teto:
                    return f"O limite diário de «{nome}» ({teto}) já foi atingido hoje."
            elif not store.uso_reservar(self.tarefa.id, nome, dia, teto):
                return f"O limite diário de «{nome}» ({teto}) já foi atingido hoje."

        if not simulacao:
            self.passos += 1
        return None
