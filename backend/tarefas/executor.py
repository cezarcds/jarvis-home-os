"""Executa uma tarefa: sequencial, para na primeira falha, verifica cada passo por código.

Garantias (cada uma tem teste):
- Passos rodam um depois do outro. A primeira falha encerra a execução; nada depois dela roda.
- Toda chamada passa pelo gate com o contrato da tarefa. Fora do contrato -> a execução PAUSA
  (ou cancela, se o contrato disser `cancelar`), sem executar o passo.
- Item repetido nunca roda de novo (chave de idempotência). Item de execução interrompida no meio é
  tratado como INCERTO e a tarefa pausa, em vez de arriscar duplicar um envio.
- Retry com espera só para falha DEFINITIVA da ferramenta (ToolError); timeout ou erro inesperado
  deixam o item incerto e encerram.
- A parada (botão, voz, atalho) é checada antes de cada passo e de cada item, e durante as esperas.
- Dry-run (`simular`) mostra o que cada passo faria sem executar, auditar nem contar limites.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from actions import gate
from routines.tools.registry import ToolError

from . import store
from .contrato import ContratoAtivo, dentro_de
from .models import Passo, Tarefa, Verificar

log = logging.getLogger("jarvis.tarefas")

try:  # erro "esperado" do Google também é falha definitiva (não deixa o item incerto)
    from routines.google_auth import GoogleAuthError
    DEFINITIVOS: Tuple[type, ...] = (ToolError, GoogleAuthError)
except Exception:  # noqa: BLE001 - bibliotecas do Google ausentes
    DEFINITIVOS = (ToolError,)

_rodando: set = set()
_REF = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}")
_UNICA = re.compile(r"^\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}$")


@dataclass
class Resultado:
    estado: str                     # ok | falhou | pausada | cancelada | interrompida | ja_executada | ja_em_execucao
    motivo: str = ""
    execucao_id: Optional[str] = None
    passos: List[Dict[str, Any]] = field(default_factory=list)


class _Termina(Exception):
    def __init__(self, estado: str, motivo: str):
        super().__init__(motivo)
        self.estado, self.motivo = estado, motivo


# ---- placeholders ------------------------------------------------------------------------------

def _resolver(ref: str, valores: Dict[str, Any], resultados: Dict[str, Any]) -> Any:
    partes = ref.split(".")
    if len(partes) == 1:
        if ref in valores:
            return valores[ref]
        raise ValueError(f"A referência {{{ref}}} não tem valor.")
    atual: Any = resultados.get(partes[0], _FALTA)
    for k in partes[1:]:
        if atual is _FALTA or not isinstance(atual, dict) or k not in atual:
            raise ValueError(f"A referência {{{ref}}} não tem valor (o passo «{partes[0]}» não produziu «{k}»).")
        atual = atual[k]
    if atual is _FALTA:
        raise ValueError(f"A referência {{{ref}}} não tem valor.")
    return atual


_FALTA = object()


def renderizar(valor: Any, valores: Dict[str, Any], resultados: Dict[str, Any], estrito: bool = True) -> Any:
    """Troca `{ref}` pelo valor. Uma string que é SÓ um placeholder mantém o tipo (lista, número).
    Com `estrito=False` (dry-run), o que ainda não existe fica como está."""
    if isinstance(valor, str):
        m = _UNICA.match(valor)
        try:
            if m:
                return _resolver(m.group(1), valores, resultados)
            return _REF.sub(lambda mm: str(_resolver(mm.group(1), valores, resultados)), valor)
        except ValueError:
            if estrito:
                raise
            return valor
    if isinstance(valor, dict):
        return {k: renderizar(v, valores, resultados, estrito) for k, v in valor.items()}
    if isinstance(valor, list):
        return [renderizar(v, valores, resultados, estrito) for v in valor]
    return valor


def identidade(item: Any) -> str:
    """Chave de idempotência padrão de um item. Arquivo existente: caminho + modificação + tamanho
    (o mesmo nome regenerado amanhã é OUTRO item; o mesmo arquivo nunca sobe duas vezes)."""
    if isinstance(item, str):
        try:
            st = os.stat(item)
            if os.path.isfile(item):
                return f"{item}|{st.st_mtime_ns}|{st.st_size}"
        except OSError:
            pass
    return str(item)


# ---- verificação ---------------------------------------------------------------------------------

def _pegar(dados: Any, caminho: str) -> Any:
    for k in caminho.split("."):
        if not isinstance(dados, dict) or k not in dados:
            return None
        dados = dados[k]
    return dados


def verificar_passo(v: Verificar, tarefa: Tarefa, data: Any, valores: Dict[str, Any],
                    resultados: Dict[str, Any], desde: float, itens: Optional[List[Any]] = None,
                    achados: Optional[List[str]] = None) -> Optional[str]:
    """None se a pós-condição vale; senão, o motivo. Arquivos só contam se foram criados/alterados
    depois do início da execução (sobra de ontem não prova nada). Em passo com `para_cada`,
    `resultado_tem` vale para CADA item (`itens` = resultado de cada um)."""
    if v.arquivos_em:
        pasta = str(renderizar(v.arquivos_em, valores, resultados))
        pastas = tarefa.contrato.escopo.pastas
        if not dentro_de(pasta, pastas):
            return f"A pasta de verificação «{pasta}» está fora do escopo do contrato."
        base = pasta if os.path.isabs(pasta) else os.path.join(pastas[0], pasta)
        try:
            minimo = int(renderizar(v.minimo, valores, resultados))
            novos = [e for e in os.scandir(base) if e.is_file() and e.stat().st_mtime >= desde - 2]
        except (OSError, ValueError, TypeError) as exc:
            return f"Não consegui verificar os arquivos em «{pasta}»: {exc}"
        if len(novos) < minimo:
            return f"Esperava ao menos {minimo} arquivo(s) novo(s) em «{pasta}», encontrei {len(novos)}."
        if achados is not None:  # os arquivos que a verificação PROVOU que existem: o próximo passo usa esta lista
            achados.extend(sorted(os.path.join(base, e.name) for e in novos))
    if v.resultado_tem:
        for i, alvo in enumerate(itens if itens is not None else [data], start=1):
            if not _pegar(alvo, v.resultado_tem):
                onde = f" (item {i})" if itens is not None else ""
                return f"O resultado{onde} não trouxe «{v.resultado_tem}»."
    return None


# ---- execução ---------------------------------------------------------------------------------------

async def _esperar(ctx: gate.Contexto, segundos: float, dormir) -> None:
    """Espera em fatias curtas para a parada valer durante o retry."""
    restante = segundos
    while restante > 0:
        gate.vivo(ctx)
        fatia = min(1.0, restante)
        await dormir(fatia)
        restante -= fatia
    gate.vivo(ctx)


async def _chamar(passo: Passo, params: Dict[str, Any], ctx: gate.Contexto, chave: Optional[str],
                  tarefa: Tarefa, execucao_id: str, relogio, dormir) -> Any:
    """Uma chamada (um item, ou o passo inteiro): idempotência + retry. Devolve `data` do resultado."""
    lim = tarefa.contrato.limites
    if chave:
        situacao = store.item_reservar(chave, tarefa.id, execucao_id, relogio())
        if situacao == "ok":
            return _PULADO
        if situacao == "incerto":
            raise _Termina("pausada", f"O item «{chave.split(':', 2)[-1]}» ficou incerto: uma execução anterior "
                                      "foi interrompida no meio e ele pode ter sido enviado. Confira e, se NÃO foi, "
                                      "libere o item para tentar de novo.")
    tentativa = 0
    while True:
        tentativa += 1
        try:
            res = await gate.executar(passo.ferramenta, params, ctx)
        except DEFINITIVOS as exc:
            if chave:
                store.item_liberar(chave)
            if tentativa < lim.tentativas:
                await _esperar(ctx, lim.espera_s, dormir)
                if chave and store.item_reservar(chave, tarefa.id, execucao_id, relogio()) != "novo":
                    raise _Termina("pausada", "Não consegui reservar o item para nova tentativa.")
                continue
            raise _Termina("falhou", f"«{passo.id}» falhou: {exc}")
        except gate.ForaDoContrato as exc:
            if chave:
                store.item_liberar(chave)
            estado = "cancelada" if tarefa.contrato.ao_sair_do_contrato == "cancelar" else "pausada"
            raise _Termina(estado, f"Fora do contrato em «{passo.id}»: {exc}")
        except gate.ConfirmacaoPendente as pend:
            if chave:
                store.item_liberar(chave)
            gate.descartar(pend.pendente["id"], "tarefa pausada: exige confirmação")
            raise _Termina("pausada", f"«{passo.id}» exige confirmação ({pend.pendente['texto']}). "
                                      "Nada foi executado.")
        except gate.ExecucaoCancelada as exc:
            if chave and not exc.iniciou:
                store.item_liberar(chave)  # nada começou: o item continua pendente, sem incerteza
            raise
        except gate.AcaoNegada as exc:
            if chave:
                store.item_liberar(chave)
            raise _Termina("falhou", f"«{passo.id}» não pôde executar: {exc}")
        except asyncio.TimeoutError:
            raise _Termina("falhou", f"«{passo.id}» passou do tempo. O item ficou incerto até você conferir.")
        except Exception as exc:  # noqa: BLE001
            log.exception("Erro inesperado no passo %s", passo.id)
            raise _Termina("falhou", f"«{passo.id}» falhou de forma inesperada ({type(exc).__name__}). "
                                     "O item ficou incerto até você conferir.")
        if chave:
            store.item_concluir(chave)
        return res.get("data", {}) if isinstance(res, dict) else {}


_PULADO = object()


async def executar_tarefa(tarefa: Tarefa, *, disparo: Optional[str] = None,
                          relogio: Callable[[], float] = time.time,
                          dormir: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> Resultado:
    if tarefa.id in _rodando:
        return Resultado("ja_em_execucao", "Esta tarefa já está em execução.")
    disparo = disparo or f"manual:{uuid.uuid4().hex[:8]}"
    eid = store.iniciar_execucao(tarefa.id, disparo, relogio())
    if eid is None:
        return Resultado("ja_executada", "Esta rodada já foi executada.")

    _rodando.add(tarefa.id)
    desde = time.time()
    ctx = gate.Contexto(sid=f"tarefa:{tarefa.id}:{eid}", origem="agendador",
                        contrato=ContratoAtivo(tarefa, relogio=relogio))
    log_passos: List[Dict[str, Any]] = []
    estado, motivo = "ok", ""
    try:
        if not tarefa.contrato.aprovado:
            raise _Termina("pausada", "O contrato desta tarefa ainda não foi aprovado.")
        valores = dict(tarefa.parametros)
        fuso = ZoneInfo(tarefa.agenda.fuso) if tarefa.agenda else ZoneInfo("America/Sao_Paulo")
        valores["data"] = datetime.fromtimestamp(relogio(), fuso).strftime("%Y-%m-%d")
        resultados: Dict[str, Any] = {}
        for passo in tarefa.passos:
            gate.vivo(ctx)
            entrada: Dict[str, Any] = {"id": passo.id, "estado": "ok", "itens": 0, "pulados": 0}
            log_passos.append(entrada)
            t0 = time.monotonic()
            try:
                if passo.para_cada:
                    lista = renderizar(passo.para_cada, valores, resultados)
                    if not isinstance(lista, list):
                        raise _Termina("falhou", f"«{passo.id}»: para_cada precisa resolver para uma lista.")
                    saidas = []
                    for item in lista:
                        gate.vivo(ctx)
                        params = renderizar(passo.params, {**valores, "item": item}, resultados)
                        sufixo = renderizar(passo.chave, {**valores, "item": item}, resultados) if passo.chave \
                            else identidade(item)
                        chave = f"{tarefa.id}:{passo.id}:{sufixo}"
                        out = await _chamar(passo, params, ctx, chave, tarefa, eid, relogio, dormir)
                        if out is _PULADO:
                            entrada["pulados"] += 1
                        else:
                            entrada["itens"] += 1
                            saidas.append(out)
                    data: Any = {"itens": saidas}
                else:
                    params = renderizar(passo.params, valores, resultados)
                    chave = f"{tarefa.id}:{passo.id}:{renderizar(passo.chave, valores, resultados)}" if passo.chave else None
                    out = await _chamar(passo, params, ctx, chave, tarefa, eid, relogio, dormir)
                    if out is _PULADO:
                        entrada["pulados"] += 1
                        data = resultados.get(passo.id, {})
                    else:
                        entrada["itens"] += 1
                        data = out
                resultados[passo.id] = data
                if passo.verificar and not (entrada["pulados"] and not entrada["itens"]):
                    achados: List[str] = []
                    falha = verificar_passo(passo.verificar, tarefa, data, valores, resultados, desde,
                                            itens=data["itens"] if passo.para_cada else None, achados=achados)
                    if falha:
                        raise _Termina("falhou", f"Verificação de «{passo.id}» falhou: {falha}")
                    if achados and isinstance(data, dict) and "arquivos" not in data:
                        # Ferramentas como comando.rodar não devolvem a lista de arquivos: quem prova é a verificação.
                        data = resultados[passo.id] = {**data, "arquivos": achados}
            except _Termina as t:
                entrada["estado"] = t.estado
                raise
            except ValueError as exc:  # placeholder sem valor
                entrada["estado"] = "falhou"
                raise _Termina("falhou", str(exc))
            except gate.ExecucaoCancelada:
                entrada["estado"] = "cancelada"
                raise
            finally:
                entrada["ms"] = int((time.monotonic() - t0) * 1000)
    except _Termina as t:
        estado, motivo = t.estado, t.motivo
    except gate.ExecucaoCancelada:
        estado, motivo = "cancelada", "Interrompida pelo botão de parada."
    except asyncio.CancelledError:
        store.finalizar(eid, "interrompida", "O Jarvis foi encerrado durante a execução.", log_passos, relogio())
        _rodando.discard(tarefa.id)
        gate.limpar_contaminacao(ctx.sid)
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Erro inesperado na tarefa %s", tarefa.id)
        estado, motivo = "falhou", f"Erro inesperado ({type(exc).__name__}); veja o log do backend."
    finally:
        _rodando.discard(tarefa.id)
        gate.limpar_contaminacao(ctx.sid)

    store.finalizar(eid, estado, motivo, log_passos, relogio())
    _auditar_fim(tarefa, eid, estado, motivo)
    return Resultado(estado, motivo, eid, log_passos)


def _auditar_fim(tarefa: Tarefa, eid: str, estado: str, motivo: str) -> None:
    try:
        from connections import db

        db.audit(f"tarefa.{estado}", f"{tarefa.id} {eid} {motivo}"[:480])
    except Exception:  # noqa: BLE001
        log.exception("Falha ao auditar o fim da tarefa %s", tarefa.id)


# ---- dry-run -------------------------------------------------------------------------------------------

def simular(tarefa: Tarefa, relogio: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Mostra o plano: o que cada passo faria e se o gate/contrato deixariam. Não executa nada, não
    audita ferramenta, não conta limites e não grava execução."""
    ctx = gate.Contexto(sid=f"simulacao:{tarefa.id}", origem="agendador",
                        contrato=ContratoAtivo(tarefa, relogio=relogio))
    valores = dict(tarefa.parametros)
    passos: List[Dict[str, Any]] = []
    tudo_ok = bool(tarefa.contrato.aprovado)
    for p in tarefa.passos:
        params = renderizar(p.params, {**valores, "item": "{item}", "data": "{data}"}, {}, estrito=False)
        av = gate.avaliar(p.ferramenta, params, ctx)
        item = {"id": p.id, "ferramenta": p.ferramenta, "params": params, "para_cada": p.para_cada,
                "permitido": av["permitido"], "motivo": av["motivo"], "nivel": av["nivel"],
                "exige_confirmacao": av["exige_confirmacao"], "verificar": p.verificar.model_dump() if p.verificar else None}
        if av["permitido"] and av["exige_confirmacao"]:
            item["motivo"] = "Exigiria confirmação: a execução pararia (pausada) neste passo."
        tudo_ok = tudo_ok and av["permitido"] and not av["exige_confirmacao"]
        passos.append(item)
    return {"tarefa": tarefa.id, "contrato_aprovado": tarefa.contrato.aprovado, "rodaria_sem_pausar": tudo_ok,
            "passos": passos,
            "aviso": "Passos com para_cada dependem do resultado dos anteriores; aqui aparecem sem os itens reais."}
