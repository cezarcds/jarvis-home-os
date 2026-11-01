"""Executa rotinas: roda os passos em paralelo, monta os blocos da tela e a fala."""
import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import llm
from actions import gate
from .google_auth import GoogleAuthError
from .models import Fala, Routine, Step, Tela
from .tools import REGISTRY, ToolError, coerce_params
from .tools.util import DIAS, TZ

log = logging.getLogger("jarvis.engine")

PERSONA = (
    "Você é JARVIS, um assistente residencial sofisticado, calmo e levemente irônico. "
    "Fale sempre em português do Brasil."
)


async def _run_step(step: Step, ctx: gate.Contexto) -> Dict[str, Any]:
    t = REGISTRY.get(step.ferramenta)
    titulo = t.rotulo.capitalize() if t else step.ferramenta
    try:
        # Toda ferramenta passa pelo gate; rotinas só podem nível 0 (max_nivel do contexto).
        res = await gate.executar(step.ferramenta, step.params, ctx)
        return {"id": step.id, "ok": True, **res}
    except gate.ExecucaoCancelada:
        return {"id": step.id, "ok": False, "titulo": titulo, "erro": "Interrompido"}
    except gate.ConfirmacaoPendente:  # não acontece com max_nivel=0; falha fechada se acontecer
        return {"id": step.id, "ok": False, "titulo": titulo, "erro": "Exige confirmação"}
    except (gate.AcaoNegada, ToolError, GoogleAuthError) as exc:
        return {"id": step.id, "ok": False, "titulo": titulo, "erro": str(exc)}
    except asyncio.TimeoutError:
        return {"id": step.id, "ok": False, "titulo": titulo, "erro": "Tempo esgotado"}
    except Exception:  # noqa: BLE001
        log.exception("Passo %s (%s) falhou", step.id, step.ferramenta)
        return {"id": step.id, "ok": False, "titulo": titulo,
                "erro": "Falha inesperada (veja o log do backend)"}


def _blocos(routine: Routine, results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordem = routine.tela.blocos or [s.id for s in routine.passos]
    blocos = []
    for sid in ordem:
        r = results.get(sid)
        if not r:
            continue
        if r["ok"]:
            blocos.append({"id": sid, "type": r["type"], "title": r["title"], "data": r["data"]})
        else:
            blocos.append({"id": sid, "type": "erro", "title": r["titulo"], "data": {"mensagem": r["erro"]}})
    return blocos


def _fala_template(results: List[Dict[str, Any]]) -> str:
    ok = [r["falado"] for r in results if r["ok"]]
    falhas = [r for r in results if not r["ok"]]
    if not ok:
        return "Não consegui obter os dados desta rotina. Os detalhes estão na tela."
    texto = " ".join(ok)
    if falhas:
        texto += " Não consegui consultar: " + ", ".join(f["titulo"].lower() for f in falhas) + "."
    return texto


async def _fala_resumo(routine: Routine, results: List[Dict[str, Any]]) -> str:
    agora = datetime.now(TZ)
    dados = []
    for r in results:
        if r["ok"]:
            dados.append(f"[{r['title']}]\n{r['resumo_llm'][:2500]}")
        else:
            dados.append(f"[{r['titulo']}] FALHOU: {r['erro']}")
    owner = os.getenv("VITE_OWNER_NAME", "").strip() or os.getenv("JARVIS_OWNER_NAME", "").strip()
    prompt = (
        "Resuma os dados abaixo em 2 a 4 frases curtas, em português do Brasil, para serem FALADAS em voz alta "
        "(sem markdown, listas, emojis ou URLs). Comece pelo mais urgente ou mais próximo no tempo. "
        "Não invente nada que não esteja nos dados. Se alguma fonte falhou, mencione isso em poucas palavras."
        + (f" Chame o usuário de {owner} no máximo uma vez." if owner else "")
        + (f"\nInstrução extra desta rotina: {routine.fala.instrucao}" if routine.fala.instrucao else "")
        + f"\nAgora: {DIAS[agora.weekday()]}, {agora.strftime('%d/%m/%Y %H:%M')}."
        + f"\nRotina: {routine.nome}\n\nDADOS:\n" + "\n\n".join(dados)
    )
    texto, _ = await llm.complete([{"role": "user", "content": prompt}], system=PERSONA,
                                  max_tokens=350, temperature=0.5, timeout=15)
    return texto


async def run_routine(routine: Routine, sid: str = "") -> Dict[str, Any]:
    t0 = time.time()
    if routine.tipo != "leitura":
        raise ToolError("Rotinas de ação ainda não estão habilitadas")
    # Um contexto para a rotina toda: a parada vale para todos os passos. Os passos ainda rodam em
    # paralelo (execução sequencial é Fase 2); cada um checa o cancelamento antes de começar.
    ctx = gate.Contexto(sid=sid, origem="rotina", max_nivel=0)
    outs = await asyncio.gather(*[_run_step(s, ctx) for s in routine.passos])
    results = {o["id"]: o for o in outs}
    ordenados = [results[s.id] for s in routine.passos]

    fala = ""
    modo = routine.fala.modo
    if modo != "nenhuma":
        if modo == "resumo" and any(r["ok"] for r in ordenados):
            try:
                fala = await _fala_resumo(routine, ordenados)
            except Exception as exc:  # noqa: BLE001
                log.warning("Resumo por LLM falhou (%s); usando template", str(exc)[:200])
                fala = _fala_template(ordenados)
        else:
            fala = _fala_template(ordenados)

    return {
        "rotina": {"id": routine.id, "nome": routine.nome},
        "titulo": routine.tela.titulo or routine.nome,
        "blocos": _blocos(routine, results),
        "fala": fala,
        "duracao_ms": int((time.time() - t0) * 1000),
    }


def rotina_avulsa(ferramenta: str, params: Dict[str, Any]) -> Routine:
    """Rotina de um passo só, para pedidos pontuais ('que reuniões tenho amanhã?')."""
    t = REGISTRY[ferramenta]
    return Routine(
        id="avulsa", nome=t.rotulo.capitalize(),
        passos=[Step(id="r", ferramenta=ferramenta, params=params)],
        tela=Tela(titulo=t.rotulo.capitalize(), blocos=["r"]), fala=Fala(modo="resumo"),
    )
