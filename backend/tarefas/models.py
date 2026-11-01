"""Modelo da tarefa e do contrato (schema versionado).

Regras do schema:
- `schema` é a versão do FORMATO. Arquivos antigos passam por `migrar()` antes de validar; versão
  mais nova que a suportada é recusada (nunca interpretar às cegas um formato futuro).
- Todos os modelos são fechados (`extra="forbid"`): um campo com erro de digitação é recusado, em
  vez de ser ignorado em silêncio e deixar um limite sem efeito.
- Placeholders `{nome}` nos parâmetros dos passos referenciam `parametros` da tarefa ou o resultado
  de um passo anterior (`{gerar.arquivos}`, lido de `data` do resultado da ferramenta). Num passo
  com `para_cada`, `{item}` é o item atual; `{data}` é o dia da execução.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_ATUAL = 1
RESERVADOS = frozenset({"data"})  # valores que o executor fornece: {data} = dia da execução (AAAA-MM-DD)

_ID = r"^[a-z0-9][a-z0-9_-]{0,47}$"
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class _Fechado(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Agenda(_Fechado):
    cron: str = Field(min_length=9, max_length=100)           # 5 campos: min hora dia mês dia-da-semana
    fuso: str = "America/Sao_Paulo"
    tolerancia_min: int = Field(default=30, ge=0, le=24 * 60)  # atraso máximo para ainda executar a rodada

    @model_validator(mode="after")
    def _valida(self):
        from . import cron  # import tardio: cron não depende deste módulo

        cron.parse(self.cron)  # levanta ValueError com mensagem amigável
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(self.fuso)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"fuso desconhecido: {self.fuso}") from exc
        return self


class Escopo(_Fechado):
    ferramentas: List[str] = Field(min_length=1, max_length=40)  # só estas podem rodar
    pastas: List[str] = Field(default_factory=list, max_length=20)
    dominios: List[str] = Field(default_factory=list, max_length=20)
    contas: List[str] = Field(default_factory=list, max_length=20)


class JanelaHorario(_Fechado):
    inicio: str
    fim: str

    @field_validator("inicio", "fim")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("use HH:MM (ex.: 09:30)")
        return v


class Limites(_Fechado):
    max_passos: int = Field(default=50, ge=1, le=500)            # chamadas de ferramenta por execução
    timeout_min: int = Field(default=60, ge=1, le=24 * 60)       # tempo total da execução
    janela_horario: Optional[JanelaHorario] = None               # só executa dentro desta janela
    por_dia: Dict[str, int] = Field(default_factory=dict)        # ferramenta -> máximo de chamadas por dia
    visibilidade: Optional[str] = None                           # valor exigido se a ferramenta tiver o parâmetro
    max_chamadas_ia: Optional[int] = Field(default=None, ge=0)   # reservado: ainda NÃO aplicado (Fase 5)
    tentativas: int = Field(default=2, ge=1, le=5)               # por passo, só para falha definitiva (ToolError)
    espera_s: float = Field(default=30.0, ge=0, le=3600)         # espera entre tentativas

    @field_validator("por_dia")
    @classmethod
    def _por_dia(cls, v: Dict[str, int]) -> Dict[str, int]:
        if any((not isinstance(n, int)) or n < 0 for n in v.values()):
            raise ValueError("por_dia: use números inteiros, zero ou maiores")
        return v


class Contrato(_Fechado):
    escopo: Escopo
    limites: Limites = Field(default_factory=Limites)
    ao_sair_do_contrato: Literal["pausar_e_perguntar", "cancelar"] = "pausar_e_perguntar"
    # O usuário precisa aprovar o contrato (uma vez) antes de a tarefa poder rodar sozinha.
    aprovado: bool = False


class Verificar(_Fechado):
    """Pós-condição checada por código (nunca perguntar ao LLM 'deu certo?')."""
    arquivos_em: Optional[str] = None            # pasta (relativa à 1ª pasta do escopo, ou absoluta dentro dele)
    minimo: Any = 1                              # número ou "{parametro}"
    resultado_tem: Optional[str] = None          # chave que precisa existir e não ser vazia em `data` do resultado

    @model_validator(mode="after")
    def _algo(self):
        if not self.arquivos_em and not self.resultado_tem:
            raise ValueError("verificar precisa de arquivos_em ou resultado_tem")
        return self


class Passo(_Fechado):
    id: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    ferramenta: str
    params: Dict[str, Any] = Field(default_factory=dict)
    verificar: Optional[Verificar] = None
    para_cada: Optional[str] = None              # "{gerar.arquivos}": repete o passo por item (idempotente por item)
    # Chave de idempotência (template). Sem ela: passo com para_cada usa a IDENTIDADE do item (arquivo =
    # caminho + data de modificação + tamanho; outro valor = ele mesmo); passo sem para_cada roda sempre.
    # Ex.: "{data}:{item}" = no máximo uma vez por dia por item.
    chave: Optional[str] = None


class Confianca(_Fechado):
    execucoes_ok: int = Field(default=0, ge=0)
    promover_apos: int = Field(default=10, ge=1)  # usado só na Fase 5 (escada de confiança)


class Tarefa(_Fechado):
    schema_: int = Field(default=SCHEMA_ATUAL, alias="schema")
    id: str = Field(pattern=_ID)
    nome: str = Field(min_length=1, max_length=80)
    agenda: Optional[Agenda] = None              # sem agenda: só roda manualmente
    parametros: Dict[str, Any] = Field(default_factory=dict)
    contrato: Contrato
    passos: List[Passo] = Field(min_length=1, max_length=30)
    confianca: Confianca = Field(default_factory=Confianca)
    ativa: bool = True

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _consistencia(self):
        if self.schema_ != SCHEMA_ATUAL:
            raise ValueError(f"schema {self.schema_} não suportado (use {SCHEMA_ATUAL})")
        ids = [p.id for p in self.passos]
        if len(set(ids)) != len(ids):
            raise ValueError("ids de passos duplicados")
        antes: set = set()
        for p in self.passos:
            for ref in _refs(p.params) | _refs(p.para_cada) | _refs(p.chave) | _refs(p.verificar.minimo if p.verificar else None):
                origem = ref.split(".", 1)[0]
                if "." in ref and origem not in antes:
                    raise ValueError(f"passo {p.id} usa {{{ref}}}, mas {origem} não vem antes dele")
                if "." not in ref and ref not in self.parametros and ref not in RESERVADOS \
                        and not (ref == "item" and p.para_cada):
                    raise ValueError(f"passo {p.id} usa {{{ref}}}, que não está em parametros")
            antes.add(p.id)
        fora = [p.ferramenta for p in self.passos if p.ferramenta not in self.contrato.escopo.ferramentas]
        if fora:
            raise ValueError(f"passos usam ferramentas fora do escopo do contrato: {sorted(set(fora))}")
        return self

    def dump(self) -> Dict[str, Any]:
        return self.model_dump(by_alias=True)


# ---- placeholders ---------------------------------------------------------------------------------

_REF = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}")


def _refs(valor: Any) -> set:
    if isinstance(valor, str):
        return set(_REF.findall(valor))
    if isinstance(valor, dict):
        return set().union(*[_refs(v) for v in valor.values()]) if valor else set()
    if isinstance(valor, (list, tuple)):
        return set().union(*[_refs(v) for v in valor]) if valor else set()
    return set()


# ---- migração de schema -----------------------------------------------------------------------------

# versão N -> função que devolve os dados na versão N+1. Vazio enquanto só existe a versão 1.
MIGRACOES: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


class SchemaNaoSuportado(ValueError):
    pass


def migrar(dados: Dict[str, Any]) -> Dict[str, Any]:
    """Sobe os dados até SCHEMA_ATUAL. Sem `schema`, assume 1. Versão futura é recusada."""
    if not isinstance(dados, dict):
        raise SchemaNaoSuportado("a tarefa precisa ser um objeto JSON")
    dados = dict(dados)
    versao = dados.get("schema", 1)
    if not isinstance(versao, int) or isinstance(versao, bool) or versao < 1:
        raise SchemaNaoSuportado(f"schema inválido: {versao!r}")
    if versao > SCHEMA_ATUAL:
        raise SchemaNaoSuportado(
            f"schema {versao} é mais novo que o suportado ({SCHEMA_ATUAL}). Atualize o Jarvis antes de importar.")
    while versao < SCHEMA_ATUAL:
        dados = MIGRACOES[versao](dados)
        versao += 1
        dados["schema"] = versao
    dados.setdefault("schema", SCHEMA_ATUAL)
    return dados


def carregar(dados: Dict[str, Any]) -> Tarefa:
    """JSON (dict) -> Tarefa validada, já migrada."""
    return Tarefa.model_validate(migrar(dados))
