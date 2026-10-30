"""Criação e edição de rotinas por linguagem natural (fluxo: rascunho -> confirmação -> gravação)."""
import json
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

import llm
from . import store
from .models import Routine
from .textutil import normalize
from .tools import REGISTRY, ToolError, catalog, coerce_params

log = logging.getLogger("jarvis.creator")

PENDING: Dict[str, Dict[str, Any]] = {}  # session_id -> rascunho aguardando confirmação
PENDING_TTL = 300

CONFIRMA = {"confirma", "confirmo", "confirmar", "sim", "pode", "pode sim", "pode salvar", "pode criar",
            "pode apagar", "salva", "salvar", "grava", "gravar", "isso", "isso mesmo", "fechado", "manda ver"}
CANCELA = {"cancela", "cancelar", "nao", "deixa", "deixa pra la", "esquece", "descarta", "melhor nao", "para"}

_VERBOS_CRIAR = r"(cri\w+|nov[ao]|faz|fazer|monta\w*|configur\w+|cadastr\w+)"
_VERBOS_EDITAR = r"(adicion\w+|inclu\w+|coloc\w+|remov\w+|tir\w+|retir\w+|alter\w+|mud\w+|renome\w+|edit\w+|atualiz\w+|apag\w+|exclu\w+|delet\w+|desativ\w+|reativ\w+|ativ\w+)"
_RE_CRIAR = re.compile(rf"\b{_VERBOS_CRIAR}\b.*\brotina\b|\brotina\b.*\bnova\b")
_RE_EDITAR = re.compile(rf"\b{_VERBOS_EDITAR}\b.*\brotina\b")
_RE_REFINAR = re.compile(r"\b(adicion\w+|inclu\w+|coloc\w+|remov\w+|tir\w+|retir\w+|troc\w+|mud\w+|alter\w+|renome\w+)\b|\b(gatilho|nome|passo)\b")
_RE_LISTAR = re.compile(r"\b(quais|lista\w*|mostr\w+|ver|minhas)\b.*\brotinas\b")


def eh_comando_de_rotina(texto: str) -> bool:
    n = normalize(texto)
    return bool(_RE_CRIAR.search(n) or _RE_EDITAR.search(n))


def eh_listagem(texto: str) -> bool:
    return bool(_RE_LISTAR.search(normalize(texto)))


def eh_confirmacao(texto: str) -> bool:
    n = normalize(texto)
    return n in CONFIRMA or n.startswith(("confirma", "pode salvar", "pode criar", "pode apagar", "sim "))


def eh_cancelamento(texto: str) -> bool:
    n = normalize(texto)
    return n in CANCELA or n.startswith(("cancel", "nao ", "deixa "))


def eh_refinamento(texto: str) -> bool:
    return bool(_RE_REFINAR.search(normalize(texto)))


def get_pending(session_id: str) -> Optional[Dict[str, Any]]:
    p = PENDING.get(session_id)
    if p and p["expira"] < time.time():
        PENDING.pop(session_id, None)
        return None
    return p


def clear_pending(session_id: str) -> None:
    PENDING.pop(session_id, None)


_SYSTEM = (
    "Você converte pedidos em português em definições de ROTINAS do assistente JARVIS. "
    "Responda SOMENTE com um objeto JSON válido, sem texto antes ou depois.\n\n"
    'Formato: {"acao":"criar|atualizar|apagar|ativar|desativar","alvo":"id de rotina existente ou null ao criar",'
    '"rotina":{...}|null,"faltando":["fontes pedidas que NÃO existem no catálogo"],"observacao":"frase curta"}\n\n'
    'Campos de "rotina": nome, descricao, gatilhos (4 a 8 frases curtas e naturais, minúsculas, com o mesmo sentido), '
    'tipo (sempre "leitura"), passos [{"id":"snake_case","ferramenta":"<nome no catálogo>","params":{}}], '
    'tela {"titulo":"...","blocos":["ids dos passos, na ordem em que aparecem"]}, '
    'fala {"modo":"resumo","instrucao":null}.\n\n'
    "Regras: use APENAS ferramentas do catálogo. Se o usuário pedir uma fonte que não existe (ex.: TikTok, Instagram, "
    "Zoho), NÃO invente: coloque em 'faltando' e crie a rotina só com o que existe. Ações que alteram dados "
    "(arquivar, apagar, enviar, publicar, limpar caixa) ainda não existem: coloque em 'faltando'. "
    "Para 'atualizar', devolva a rotina COMPLETA já modificada, mantendo o que não foi pedido para mudar. "
    "Para apagar/ativar/desativar, 'rotina' é null e 'alvo' é o id da rotina existente."
)


def _catalogo_texto() -> str:
    linhas = ["CATÁLOGO DE FERRAMENTAS DISPONÍVEIS:"]
    for t in catalog(only_available=True, leitura_only=True):
        ps = "; ".join(f"{p['nome']}:{p['tipo']}={p['default']}" for p in t["params"])
        linhas.append(f"- {t['nome']} ({t['rotulo']}): {t['descricao']} | params: {ps or 'nenhum'}")
    indisp = [t for t in catalog(leitura_only=True) if not t["disponivel"]]
    if indisp:
        linhas.append("INDISPONÍVEIS AGORA (trate como 'faltando'): " + ", ".join(t["nome"] for t in indisp))
    return "\n".join(linhas)


def _existentes_texto() -> str:
    linhas = ["ROTINAS EXISTENTES:"]
    for r in store.list_routines():
        linhas.append(
            f"- id={r.id} | {r.nome} | ativa={r.ativa} | gatilhos={r.gatilhos[:4]} | "
            f"passos={[s.ferramenta for s in r.passos]}"
        )
    return "\n".join(linhas)


def _resolver_alvo(alvo: Optional[str]) -> Optional[Routine]:
    if not alvo:
        return None
    r = store.get(alvo)
    if r:
        return r
    na = normalize(alvo)
    return next((x for x in store.list_routines() if normalize(x.nome) == na or normalize(x.id) == na), None)


def _validar(raw: Dict[str, Any]) -> Routine:
    raw = dict(raw)
    raw.pop("id", None)
    raw.pop("criada_em", None)
    raw.pop("atualizada_em", None)
    if raw.get("tipo", "leitura") != "leitura":
        raise ValueError("rotinas de ação ainda não são suportadas")
    raw["tipo"] = "leitura"
    r = Routine.model_validate(raw)
    for s in r.passos:
        t = REGISTRY.get(s.ferramenta)
        if not t:
            raise ValueError(f"ferramenta inexistente: {s.ferramenta}")
        coerce_params(t, s.params)  # valida tipos
        s.params = {k: v for k, v in s.params.items() if k in {p.name for p in t.params}}
    if not r.tela.blocos:
        r.tela.blocos = [s.id for s in r.passos]
    return r


def descrever(acao: str, rotina: Optional[Routine], alvo: Optional[Routine], faltando: list) -> str:
    if acao == "apagar":
        return f"Vou apagar a rotina {alvo.nome}. Confirma?"
    if acao in ("ativar", "desativar"):
        return f"Vou {acao} a rotina {alvo.nome}. Confirma?"
    fontes = ", ".join(REGISTRY[s.ferramenta].rotulo for s in rotina.passos)
    gat = " ou ".join(f"'{g}'" for g in rotina.gatilhos[:2]) or "um gatilho que você definir"
    verbo = "atualizar" if acao == "atualizar" else "criar"
    txt = f"Vou {verbo} a rotina {rotina.nome}. Quando você disser {gat}, eu consulto: {fontes}."
    if faltando:
        txt += " Ainda não tenho integração com: " + ", ".join(faltando) + "."
    return txt + " Confirma?"


async def rascunhar(session_id: str, instrucao: str, base: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    """Gera um rascunho a partir da fala do usuário. Retorna (texto_falado, bloco_rascunho)."""
    prompt = f"{_catalogo_texto()}\n\n{_existentes_texto()}\n\n"
    if base:
        prompt += f"RASCUNHO ATUAL (ajuste conforme o pedido):\n{json.dumps(base, ensure_ascii=False)}\n\n"
    prompt += f"PEDIDO: {instrucao}"
    erro = ""
    for tentativa in range(2):
        msgs = [{"role": "user", "content": prompt + (f"\n\nSua resposta anterior era inválida: {erro}. Corrija." if erro else "")}]
        try:
            raw, _ = await llm.complete(msgs, system=_SYSTEM, max_tokens=1500, temperature=0.2, timeout=25)
            obj = llm.extract_json(raw)
            acao = obj.get("acao")
            if acao not in ("criar", "atualizar", "apagar", "ativar", "desativar"):
                raise ValueError("acao inválida")
            faltando = [str(x) for x in (obj.get("faltando") or [])][:6]
            alvo = _resolver_alvo(obj.get("alvo"))
            rotina = None
            if acao in ("criar", "atualizar"):
                if not isinstance(obj.get("rotina"), dict):
                    raise ValueError("faltou o campo rotina")
                rotina = _validar(obj["rotina"])
                if acao == "atualizar" and not alvo:
                    raise ValueError("rotina a atualizar não encontrada")
            elif not alvo:
                raise ValueError("rotina alvo não encontrada")
            break
        except Exception as exc:  # noqa: BLE001
            erro = str(exc)[:200]
            log.warning("Rascunho inválido (tentativa %d): %s", tentativa + 1, erro)
            if tentativa == 1:
                return ("Não consegui montar essa rotina. Tente descrever de novo, dizendo quando ela dispara e "
                        "quais fontes consultar.", {"type": "erro", "title": "Rotina", "data": {"mensagem": erro}})

    if acao == "atualizar":
        rotina.id = alvo.id
    PENDING[session_id] = {
        "acao": acao, "alvo_id": alvo.id if alvo else None, "rotina": rotina.model_dump() if rotina else None,
        "faltando": faltando, "expira": time.time() + PENDING_TTL,
    }
    texto = descrever(acao, rotina, alvo, faltando)
    bloco = {
        "type": "rascunho", "title": "Confirme a rotina",
        "data": {
            "acao": acao, "alvo": alvo.nome if alvo else None, "faltando": faltando,
            "rotina": rotina.model_dump() if rotina else None,
            "passos": [REGISTRY[s.ferramenta].rotulo for s in rotina.passos] if rotina else [],
        },
    }
    return texto, bloco


def confirmar(session_id: str) -> Tuple[str, Dict[str, Any]]:
    p = get_pending(session_id)
    if not p:
        return "Não há nada pendente para confirmar.", {}
    clear_pending(session_id)
    acao = p["acao"]
    if acao in ("criar", "atualizar"):
        r = Routine.model_validate(p["rotina"])
        if acao == "atualizar":
            r.id = p["alvo_id"]
        else:
            r.id = ""
        salvo = store.upsert(r)
        gat = salvo.gatilhos[0] if salvo.gatilhos else None
        txt = f"Rotina {salvo.nome} {'atualizada' if acao == 'atualizar' else 'criada'}."
        if gat:
            txt += f" É só dizer {gat}."
        return txt, {"type": "rotina", "title": "Rotina salva", "data": {"rotina": salvo.model_dump()}}
    alvo = store.get(p["alvo_id"])
    if not alvo:
        return "Essa rotina não existe mais.", {}
    if acao == "apagar":
        store.delete(alvo.id)
        return f"Rotina {alvo.nome} apagada.", {"type": "texto", "title": "Rotina apagada", "data": {"texto": alvo.nome}}
    alvo.ativa = acao == "ativar"
    store.upsert(alvo)
    return (f"Rotina {alvo.nome} {'ativada' if alvo.ativa else 'desativada'}.",
            {"type": "rotina", "title": "Rotina atualizada", "data": {"rotina": alvo.model_dump()}})
