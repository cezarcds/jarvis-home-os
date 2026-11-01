"""Agendador: laço dentro do backend que dispara as tarefas na hora do cron.

Garantias (cada uma tem teste):
- Cada rodada (tarefa + horário do cron) dispara UMA vez, mesmo depois de reiniciar o backend
  (UNIQUE no banco). Rodada anterior à criação da tarefa nunca roda.
- Computador desligado na hora: ao ligar, a rodada só roda se o atraso couber em `tolerancia_min` E
  ainda estivermos dentro da janela de horário do contrato; senão fica registrada como `perdida`
  (evita subir os vídeos de ontem às 22h). Só a rodada mais recente é considerada.
- Execuções que ficaram 'em andamento' quando o programa caiu viram 'interrompida' ao subir.
- A parada (botão, voz, atalho) PAUSA o agendador. A pausa sobrevive a reinício e só termina quando
  você manda retomar.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from actions import gate

from . import cron, executor, store
from .contrato import ContratoAtivo

log = logging.getLogger("jarvis.agendador")


class Agendador:
    def __init__(self, *, relogio: Callable[[], float] = time.time,
                 dormir: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                 intervalo_s: float = 20.0,
                 executar: Callable[..., Awaitable[Any]] = executor.executar_tarefa):
        self._relogio, self._dormir, self._intervalo, self._executar = relogio, dormir, intervalo_s, executar
        self._tarefas: set = set()
        self._laco: Optional[asyncio.Task] = None

    # ---- pausa ----------------------------------------------------------------------------------
    def pausar(self, motivo: str = "usuario") -> None:
        store.definir_pausa(True)
        log.info("Agendador pausado (%s)", motivo)

    def retomar(self) -> None:
        store.definir_pausa(False)
        log.info("Agendador retomado")

    @staticmethod
    def pausado() -> bool:
        return store.agendador_pausado()

    # ---- uma passada ------------------------------------------------------------------------------
    async def tick(self) -> List[asyncio.Task]:
        """Dispara o que estiver na hora. Devolve as tarefas assíncronas iniciadas (para os testes
        esperarem); o laço real não espera por elas."""
        if self.pausado():
            return []
        agora = self._relogio()
        iniciadas: List[asyncio.Task] = []
        for t in store.listar():
            if not t.ativa or not t.agenda:
                continue
            try:
                tz = ZoneInfo(t.agenda.fuso)
                slot = cron.anterior(t.agenda.cron, datetime.fromtimestamp(agora, tz), tz)
            except Exception:  # noqa: BLE001
                log.exception("Agenda inválida na tarefa %s", t.id)
                continue
            if slot is None:
                continue
            criada = store.criada_em(t.id) or 0
            if slot.timestamp() < criada:
                continue  # rodada anterior à criação da tarefa
            chave = cron.chave_slot(slot)
            if store.disparo_existe(t.id, chave):
                continue
            atraso_min = (agora - slot.timestamp()) / 60
            if atraso_min > t.agenda.tolerancia_min:
                store.iniciar_execucao(t.id, chave, agora, "perdida",
                                       f"Rodada de {chave} perdida: atraso de {int(atraso_min)} min "
                                       f"(tolerância {t.agenda.tolerancia_min} min).")
                log.warning("Tarefa %s: rodada %s perdida", t.id, chave)
                continue
            if not ContratoAtivo(t, relogio=self._relogio).na_janela():
                store.iniciar_execucao(t.id, chave, agora, "perdida",
                                       f"Rodada de {chave} perdida: fora da janela de horário do contrato.")
                continue
            iniciadas.append(self._disparar(t, chave))
        return iniciadas

    def _disparar(self, tarefa, chave: str) -> asyncio.Task:
        task = asyncio.ensure_future(self._executar(tarefa, disparo=chave, relogio=self._relogio, dormir=self._dormir))
        self._tarefas.add(task)
        task.add_done_callback(self._tarefas.discard)
        return task

    # ---- ciclo de vida -------------------------------------------------------------------------------
    def iniciar(self) -> None:
        n = store.recuperar_interrompidas(self._relogio())
        if n:
            log.warning("%d execução(ões) estavam em andamento quando o Jarvis caiu: marcadas como interrompidas.", n)
        gate.registrar_gancho_parada(lambda: self.pausar("parada"))
        self._laco = asyncio.ensure_future(self._run())

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Falha no ciclo do agendador")
            await self._dormir(self._intervalo)

    async def encerrar(self) -> None:
        for t in [self._laco, *self._tarefas]:
            if t is not None and not t.done():
                t.cancel()
        for t in [self._laco, *self._tarefas]:
            if t is not None:
                try:
                    await t
                except BaseException:  # noqa: BLE001
                    pass

    # ---- estado para o HUD ----------------------------------------------------------------------------
    def estado(self) -> Dict[str, Any]:
        agora = self._relogio()
        proximas = []
        for t in store.listar():
            if not t.ativa or not t.agenda:
                continue
            tz = ZoneInfo(t.agenda.fuso)
            nxt = cron.proxima(t.agenda.cron, datetime.fromtimestamp(agora, tz), tz)
            proximas.append({"tarefa": t.id, "proxima": nxt.isoformat() if nxt else None})
        return {"pausado": self.pausado(), "proximas": proximas, "em_execucao": len(self._tarefas)}
