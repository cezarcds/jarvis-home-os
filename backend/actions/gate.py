"""Gate: o ÚNICO ponto por onde uma ferramenta executa (regras 1 a 3, 8 a 10 do CLAUDE.md).

Voz, texto, roteador por LLM, rotinas e (no futuro) o agendador chamam `executar()`. Nada chama
`Tool.fn` fora deste módulo; um teste varre o código e falha se alguém fizer isso.

A política vive aqui, em código; o prompt do modelo não decide nada:

    nível 0 leitura              executa e registra
    nível 1 acao_local           executa e registra
    nível 2 externo_reversivel   ação pendente: só executa depois de confirmação
    nível 3 externo_irreversivel ação pendente: só executa depois de confirmação por clique no HUD
    risco desconhecido           vale 3 (falha fechada)

Ação pendente: id, texto exato do que será feito, expira em 60 s, uso único. Os parâmetros ficam
guardados aqui no servidor; a confirmação só referencia o id, então ninguém troca o conteúdo entre
o pedido e o clique. Um "sim" solto, sem id, não vale.

Contrato (Fase 2): uma tarefa aprovada roda com `Contexto.contrato`. Antes de decidir qualquer coisa
o gate pergunta ao contrato (`checar`); fora dele a execução para com `ForaDoContrato`. Dentro de um
contrato aprovado o nível 2 roda sem perguntar, MAS contaminação por dado externo volta a exigir
confirmação, e o nível 3 sempre confirma.

Parada: `parar()` invalida toda execução iniciada antes dela (cada `Contexto` guarda a "geração" em
que nasceu), cancela as tarefas em andamento e descarta as confirmações pendentes. `asyncio.to_thread`
não cancela a thread sozinho: uma ação já em andamento termina, mas nada novo começa.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import secrets
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from routines.tools.registry import REGISTRY, Tool, ToolError, coerce_params, nivel_de  # noqa: F401

from .redact import redigir

log = logging.getLogger("jarvis.gate")

PENDENTE_TTL_S = 60.0
MAX_PENDENTES = 20
CONTAMINACAO_TTL_S = 3600.0
VIAS_DE_CONFIRMACAO = frozenset({"clique"})  # voz sozinha não confirma (AGENTE.md, seção 5)
_sessao_atual: contextvars.ContextVar[str] = contextvars.ContextVar("jarvis_gate_sessao", default="")


_contrato_atual: contextvars.ContextVar[Any] = contextvars.ContextVar("jarvis_gate_contrato", default=None)


def contrato_atual() -> Any:
    """Contrato da tarefa em execução (None fora de tarefa). Para a ferramenta saber, por exemplo, quais
    domínios o navegador pode abrir. É só leitura: quem aplica o contrato é o gate, antes de chamar a ferramenta."""
    return _contrato_atual.get()


def sessao_atual() -> str:
    """Sessão de quem pediu a ferramenta em execução (para a função da ferramenta saber)."""
    return _sessao_atual.get()


SESSAO_GLOBAL = ""  # contaminação de quem não identifica a sessão vale para todas


# ---- erros -----------------------------------------------------------------------

class GateErro(Exception):
    """Base dos desvios do gate. A mensagem é amigável e pode ser falada."""


class AcaoNegada(GateErro):
    """A política (ou a indisponibilidade da ferramenta) impediu a execução."""


class ForaDoContrato(AcaoNegada):
    """A ação sai do escopo ou dos limites do contrato da tarefa (padrão: pausar e perguntar)."""


class ConfirmacaoPendente(GateErro):
    """A ação exige confirmação: nada foi executado. `pendente` descreve o que mostrar ao usuário."""

    def __init__(self, pendente: Dict[str, Any]):
        super().__init__(pendente["texto"])
        self.pendente = pendente


class ConfirmacaoInvalida(GateErro):
    """Confirmação inexistente, expirada, já usada ou por via não aceita."""


class ExecucaoCancelada(GateErro):
    """O botão de parada (ou o atalho, ou a voz) interrompeu a execução.
    `iniciou` é True quando a ferramenta JÁ tinha começado (o efeito pode ter ocorrido) e False quando
    a parada pegou antes de ela começar (nada aconteceu)."""
    iniciou: bool = False


# ---- relógio e estado (trocáveis nos testes) ----------------------------------------

_clock: Callable[[], float] = time.time


def agora() -> float:
    return _clock()


_lock = threading.RLock()
_geracao = 0  # sobe a cada parar()
_pendentes: Dict[str, "Pendente"] = {}
_ativas: Dict[str, "_Ativa"] = {}
_contaminadas: Dict[str, float] = {}
_ganchos_parada: List[Callable[[], None]] = []


def reset_state() -> None:
    """Zera tudo (testes)."""
    global _geracao, _clock
    with _lock:
        _geracao = 0
        _clock = time.time
        _pendentes.clear()
        _ativas.clear()
        _contaminadas.clear()
        _ganchos_parada.clear()


# ---- contexto, pendentes ------------------------------------------------------------

@dataclass
class Contexto:
    """Quem está pedindo e em que condições. Uma execução (ex.: uma rotina com vários passos)
    usa um único Contexto, para que a parada valha para todos os passos."""
    sid: str = ""
    origem: str = "assistente"            # assistente | rotina | llm | agendador | api
    max_nivel: Optional[int] = None       # teto de risco desta origem (rotinas de leitura: 0)
    contaminado: bool = False             # dado externo já entrou neste fluxo
    contrato: Optional[Any] = None        # objeto com `aprovado: bool` e `checar(nome, params, nivel, simulacao)`
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    geracao: int = field(default_factory=lambda: _geracao)


@dataclass
class Pendente:
    id: str
    ferramenta: str
    nivel: int
    texto: str
    params: Dict[str, Any]
    ctx: Contexto
    criada: float
    expira: float
    contaminado: bool

    def publico(self) -> Dict[str, Any]:
        """O que o HUD recebe: nunca os parâmetros crus, só o texto exato a confirmar."""
        return {"id": self.id, "ferramenta": self.ferramenta, "nivel": self.nivel, "texto": self.texto,
                "forte": self.nivel >= 3, "expira_em": self.expira, "segundos": PENDENTE_TTL_S}


@dataclass
class _Ativa:
    task: Optional[asyncio.Task]
    loop: Optional[asyncio.AbstractEventLoop]


# ---- política --------------------------------------------------------------------------

def exige_confirmacao(nivel: int, contaminado: bool, contrato_ok: bool = False) -> bool:
    """Quando uma ação precisa de confirmação.

    Fase 1: não existe contrato, então `contrato_ok` é sempre False e todo nível 2 confirma.
    Fase 2: com contrato aprovado, o nível 2 dentro dele roda sem perguntar, MAS contaminação
    (dado externo lido antes) volta a exigir confirmação mesmo dentro do contrato. Nível 3 sempre.
    """
    if nivel >= 3:
        return True
    if nivel == 2:
        return contaminado or not contrato_ok
    return False


# ---- contaminação --------------------------------------------------------------------------

def marcar_contaminado(sid: str) -> None:
    with _lock:
        _contaminadas[sid or SESSAO_GLOBAL] = agora()


def sessao_contaminada(sid: str) -> bool:
    with _lock:
        agora_ = agora()
        for k in [k for k, t in _contaminadas.items() if agora_ - t > CONTAMINACAO_TTL_S]:
            del _contaminadas[k]
        return bool(sid) and sid in _contaminadas or SESSAO_GLOBAL in _contaminadas


def limpar_contaminacao(sid: str) -> None:
    with _lock:
        _contaminadas.pop(sid or SESSAO_GLOBAL, None)


# ---- auditoria -------------------------------------------------------------------------------

def _auditar(ctx: Contexto, nome: str, nivel: int, resultado: str, params: Any = None, *,
             confirmacao: str = "nenhuma", contaminado: bool = False, duracao_ms: Optional[int] = None,
             detalhe: str = "", obrigatorio: bool = False) -> None:
    """Grava o registro. Falha ao gravar bloqueia ações de nível 2+ (`obrigatorio`); nas de nível
    0 e 1 só avisa no log, para um banco com problema não impedir 'abre o Profit'."""
    try:
        from connections import db

        db.audit_action(run_id=ctx.run_id, tool=nome, nivel=nivel, resultado=resultado,
                        params=redigir(params) if params is not None else None, confirmacao=confirmacao,
                        sessao=ctx.sid, contaminado=contaminado, duracao_ms=duracao_ms, origem=ctx.origem,
                        detalhe=detalhe)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao gravar a auditoria de %s (%s)", nome, resultado)
        if obrigatorio:
            raise AcaoNegada("Não consegui registrar a auditoria desta ação, então não executei.") from None


# ---- parada ------------------------------------------------------------------------------------

def _vivo(ctx: Contexto) -> None:
    if ctx.geracao != _geracao:
        raise ExecucaoCancelada("A execução foi interrompida.")


def registrar_gancho_parada(fn: Callable[[], None]) -> None:
    """Para o que roda fora do asyncio (processo filho do Playwright, por exemplo)."""
    with _lock:
        _ganchos_parada.append(fn)


def parar(motivo: str = "usuario") -> Dict[str, int]:
    """Botão de parada. Pode ser chamado de qualquer thread (atalho global)."""
    global _geracao
    with _lock:
        _geracao += 1
        ativas = list(_ativas.items())
        pendentes = list(_pendentes.values())
        _pendentes.clear()
        ganchos = list(_ganchos_parada)
    for _, a in ativas:
        if a.task is not None and a.loop is not None:
            a.loop.call_soon_threadsafe(a.task.cancel)
    for p in pendentes:
        _auditar(p.ctx, p.ferramenta, p.nivel, "cancelado", p.params, contaminado=p.contaminado,
                 detalhe=f"parada ({motivo}) com confirmação pendente")
    for g in ganchos:
        try:
            g()
        except Exception:  # noqa: BLE001
            log.exception("Gancho de parada falhou")
    try:
        from connections import db

        db.audit("parada", f"{motivo}: {len(ativas)} em andamento, {len(pendentes)} pendentes")
    except Exception:  # noqa: BLE001
        log.exception("Falha ao auditar a parada")
    return {"em_andamento": len(ativas), "pendentes_descartadas": len(pendentes)}


_PARAR = re.compile(
    r"^(jarvis[, ]+)?(para|pare|parar|cancela|cancele|cancelar|interrompe|interrompa|interromper)\s+tudo(\s+agora)?(\s+jarvis)?$"
)


def eh_comando_parar(texto: str) -> bool:
    """'para tudo' falado ou digitado. Só a frase inteira vale: 'para' sozinho é preposição."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    t = re.sub(r"[^a-z\s,]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,")
    return bool(_PARAR.match(t))


# ---- pendentes --------------------------------------------------------------------------------

def _texto_confirmacao(t: Tool, params: Dict[str, Any]) -> str:
    if t.confirmacao:
        return t.confirmacao(params)
    partes = [f"{k}: {str(v)[:300]}" for k, v in params.items() if v is not None]
    return f"Executar «{t.rotulo}»" + (" com " + "; ".join(partes) if partes else "") + "."


def _expirar() -> None:
    """Descarta pendentes vencidas, registrando cada uma. Roda a cada acesso (sem tarefa de fundo)."""
    with _lock:
        vencidas = [p for p in _pendentes.values() if p.expira <= agora()]
        for p in vencidas:
            _pendentes.pop(p.id, None)
    for p in vencidas:
        _auditar(p.ctx, p.ferramenta, p.nivel, "expirado", p.params, contaminado=p.contaminado)


def listar_pendentes(sid: Optional[str] = None) -> List[Dict[str, Any]]:
    _expirar()
    with _lock:
        return [p.publico() for p in _pendentes.values() if sid is None or p.ctx.sid == sid]


def negar(id_: str) -> None:
    _expirar()
    with _lock:
        p = _pendentes.pop(id_, None)
    if not p:
        raise ConfirmacaoInvalida("Confirmação inexistente, expirada ou já usada.")
    _auditar(p.ctx, p.ferramenta, p.nivel, "negado", p.params, confirmacao="usuario_negou",
             contaminado=p.contaminado)


def descartar(id_: str, motivo: str) -> None:
    """Retira uma pendente sem que o usuário a tenha negado (ex.: a tarefa que a criou foi pausada).
    Fica registrada como 'cancelado', nunca como 'negado' pelo usuário."""
    with _lock:
        p = _pendentes.pop(id_, None)
    if p:
        _auditar(p.ctx, p.ferramenta, p.nivel, "cancelado", p.params, contaminado=p.contaminado, detalhe=motivo)


# ---- execução ------------------------------------------------------------------------------------

async def _rodar(t: Tool, params: Dict[str, Any], ctx: Contexto, nivel: int, contaminado: bool,
                 confirmacao: str) -> Any:
    """Roda a função da ferramenta. É aqui, e só aqui, que `Tool.fn` é chamada."""
    _vivo(ctx)
    if nivel >= 2:  # antes de agir, o registro é obrigatório: sem auditoria, não executa
        _auditar(ctx, t.name, nivel, "iniciada", params, confirmacao=confirmacao, contaminado=contaminado,
                 obrigatorio=True)
    t0 = time.monotonic()
    chave = uuid.uuid4().hex
    with _lock:
        _ativas[chave] = _Ativa(asyncio.current_task(), asyncio.get_running_loop())
    ms = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731
    token = _sessao_atual.set(ctx.sid)
    token_contrato = _contrato_atual.set(ctx.contrato)
    try:
        resultado = await asyncio.wait_for(t.fn(**params), timeout=t.timeout)
    except asyncio.CancelledError:
        _auditar(ctx, t.name, nivel, "cancelado", params, confirmacao=confirmacao, contaminado=contaminado,
                 duracao_ms=ms())
        if ctx.geracao != _geracao:
            cancelada = ExecucaoCancelada("A execução foi interrompida.")
            cancelada.iniciou = True
            raise cancelada from None
        raise
    except asyncio.TimeoutError:
        _auditar(ctx, t.name, nivel, "timeout", params, confirmacao=confirmacao, contaminado=contaminado,
                 duracao_ms=ms())
        raise
    except Exception as exc:  # noqa: BLE001 - o chamador decide a mensagem; aqui só registramos
        _auditar(ctx, t.name, nivel, "erro", params, confirmacao=confirmacao, contaminado=contaminado,
                 duracao_ms=ms(), detalhe=f"{type(exc).__name__}: {str(exc)[:200]}")
        raise
    finally:
        _sessao_atual.reset(token)
        _contrato_atual.reset(token_contrato)
        with _lock:
            _ativas.pop(chave, None)
    if t.le_dado_externo:
        marcar_contaminado(ctx.sid)
        ctx.contaminado = True  # passos seguintes da mesma execução já nascem contaminados
    _auditar(ctx, t.name, nivel, "ok", params, confirmacao=confirmacao, contaminado=contaminado, duracao_ms=ms())
    return resultado


def _preparar(nome: str, params: Optional[Dict[str, Any]], ctx: Contexto, *, auditar: bool,
              simulacao: bool = False):
    """Todas as checagens que antecedem a execução. Devolve (ferramenta, nível, parâmetros limpos,
    contaminado, contrato_ok) ou levanta AcaoNegada/ForaDoContrato/ToolError/ExecucaoCancelada.
    `auditar=False` e `simulacao=True` são para o dry-run: nada é gravado nem contabilizado."""

    def registrar(nivel_, resultado, detalhe):
        if auditar:
            _auditar(ctx, nome, nivel_, resultado, params, detalhe=detalhe)

    t = REGISTRY.get(nome)
    if t is None:
        registrar(3, "negado", "ferramenta desconhecida")
        raise AcaoNegada("Não sei executar essa ação.")
    nivel = nivel_de(t.risco)

    try:
        _vivo(ctx)
    except ExecucaoCancelada:
        registrar(nivel, "cancelado", "parada antes de começar")
        raise

    if ctx.max_nivel is not None and nivel > ctx.max_nivel:
        registrar(nivel, "negado", f"origem {ctx.origem} só permite nível {ctx.max_nivel}")
        raise AcaoNegada("Ações ainda não habilitadas")

    ok, motivo = t.disponivel()
    if not ok:
        registrar(nivel, "negado", f"indisponível: {motivo}")
        raise AcaoNegada(motivo or "Ferramenta indisponível.")

    try:
        limpos = coerce_params(t, params)
    except ToolError as exc:
        registrar(nivel, "negado", str(exc))
        raise

    if t.somente_tarefa and ctx.contrato is None:
        registrar(nivel, "negado", "ferramenta só roda dentro de uma tarefa com contrato")
        raise AcaoNegada(f"«{nome}» só roda dentro de uma tarefa com contrato aprovado.")

    if t.nunca_em_tarefa and ctx.contrato is not None:
        registrar(nivel, "negado", "ferramenta não roda dentro de tarefa")
        raise AcaoNegada(f"«{nome}» não roda dentro de tarefa: só por ação direta sua, com confirmação.")

    if ctx.contrato is not None:
        visiveis = dict(limpos)
        if t.alvos is not None:
            try:
                for k, v in t.alvos(limpos).items():
                    visiveis.setdefault(k, v)
            except ToolError as exc:
                registrar(nivel, "negado", str(exc))
                raise
        violacao = ctx.contrato.checar(nome, visiveis, nivel, simulacao=simulacao)
        if violacao:
            registrar(nivel, "negado", f"fora do contrato: {violacao}")
            raise ForaDoContrato(violacao)

    contaminado = ctx.contaminado or sessao_contaminada(ctx.sid)
    contrato_ok = ctx.contrato is not None and bool(getattr(ctx.contrato, "aprovado", False))
    return t, nivel, limpos, contaminado, contrato_ok


def avaliar(nome: str, params: Optional[Dict[str, Any]], ctx: Optional[Contexto] = None) -> Dict[str, Any]:
    """O que `executar` faria, SEM executar, auditar nem contabilizar limites (dry-run)."""
    ctx = ctx or Contexto()
    try:
        t, nivel, limpos, contaminado, contrato_ok = _preparar(nome, params, ctx, auditar=False, simulacao=True)
    except (GateErro, ToolError) as exc:
        return {"permitido": False, "motivo": str(exc), "exige_confirmacao": False, "nivel": None}
    return {"permitido": True, "motivo": "", "nivel": nivel, "params": limpos,
            "exige_confirmacao": exige_confirmacao(nivel, contaminado, contrato_ok)}


def vivo(ctx: Contexto) -> None:
    """Levanta ExecucaoCancelada se a parada foi acionada depois que `ctx` nasceu."""
    _vivo(ctx)


async def executar(nome: str, params: Optional[Dict[str, Any]], ctx: Optional[Contexto] = None) -> Any:
    """Executa uma ferramenta de acordo com a política.

    Devolve o resultado da ferramenta. Levanta AcaoNegada (ou ForaDoContrato), ConfirmacaoPendente ou
    ExecucaoCancelada quando não executa; erros da própria ferramenta (ToolError, timeout...)
    são registrados e repassados ao chamador.
    """
    ctx = ctx or Contexto()
    t, nivel, limpos, contaminado, contrato_ok = _preparar(nome, params, ctx, auditar=True)

    if exige_confirmacao(nivel, contaminado, contrato_ok):
        _expirar()
        with _lock:
            if len(_pendentes) >= MAX_PENDENTES:
                excesso = True
            else:
                excesso = False
                t0 = agora()
                p = Pendente(id=secrets.token_hex(4), ferramenta=nome, nivel=nivel,
                             texto=_texto_confirmacao(t, limpos), params=limpos, ctx=ctx, criada=t0,
                             expira=t0 + PENDENTE_TTL_S, contaminado=contaminado)
                _pendentes[p.id] = p
        if excesso:
            _auditar(ctx, nome, nivel, "negado", params, detalhe="muitas confirmações pendentes")
            raise AcaoNegada("Há confirmações demais esperando. Resolva ou espere expirarem.")
        try:
            _auditar(ctx, nome, nivel, "pendente", limpos, contaminado=contaminado, obrigatorio=True)
        except AcaoNegada:
            with _lock:
                _pendentes.pop(p.id, None)
            raise
        raise ConfirmacaoPendente(p.publico())

    return await _rodar(t, limpos, ctx, nivel, contaminado, "nenhuma")


async def confirmar(id_: str, via: str) -> Any:
    """Confirma uma ação pendente pelo id. Uso único; só a via 'clique' vale."""
    if via not in VIAS_DE_CONFIRMACAO:
        raise ConfirmacaoInvalida("Esta ação só pode ser confirmada por clique na tela.")
    _expirar()
    with _lock:
        p = _pendentes.pop(id_, None)
    if not p:
        raise ConfirmacaoInvalida("Confirmação inexistente, expirada ou já usada.")
    t = REGISTRY.get(p.ferramenta)
    if t is None:  # sumiu do catálogo entre o pedido e o clique
        _auditar(p.ctx, p.ferramenta, p.nivel, "negado", p.params, detalhe="ferramenta sumiu do catálogo")
        raise AcaoNegada("Não sei mais executar essa ação.")
    ok, motivo = t.disponivel()
    if not ok:
        _auditar(p.ctx, p.ferramenta, p.nivel, "negado", p.params, confirmacao=via, detalhe=f"indisponível: {motivo}")
        raise AcaoNegada(motivo or "Ferramenta indisponível.")
    try:
        _vivo(p.ctx)
    except ExecucaoCancelada:
        _auditar(p.ctx, p.ferramenta, p.nivel, "cancelado", p.params, confirmacao=via, detalhe="parada antes de confirmar")
        raise
    return await _rodar(t, p.params, p.ctx, p.nivel, p.contaminado, via)
