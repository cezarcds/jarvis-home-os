"""Catálogo de ferramentas que as rotinas podem usar.

Uma ferramenta é uma função assíncrona que devolve um dict:
  {"type": "agenda|emails|clima|metricas|...", "title": str, "data": {...},
   "falado": "frase para o modo template", "resumo_llm": "texto curto para o resumo por LLM"}
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


class ToolError(Exception):
    """Erro esperado, com mensagem amigável."""


# Níveis de risco (docs/AGENTE.md, seção 5). A política que decide o que cada nível exige
# vive em actions/gate.py; aqui só ficam os nomes e a tradução para número.
NIVEIS: Dict[str, int] = {
    "leitura": 0,               # listar emails, consultar GA4, ler tela permitida
    "acao_local": 1,            # abrir app, criar arquivo, rodar comando nomeado
    "externo_reversivel": 2,    # criar rascunho, upload privado, criar cartão
    "externo_irreversivel": 3,  # enviar, publicar, apagar, pagar
}


def nivel_de(risco: Any) -> int:
    """Nível numérico do risco. Risco ausente ou desconhecido vale 3 (falha fechada)."""
    return NIVEIS.get(risco, 3)


@dataclass
class Param:
    name: str
    tipo: str = "str"  # str | int | float | bool
    default: Any = None
    descricao: str = ""
    minimo: Optional[float] = None
    maximo: Optional[float] = None


@dataclass
class Tool:
    name: str
    rotulo: str  # curto, usado ao descrever rotinas em voz alta ("agenda de hoje")
    descricao: str
    params: List[Param]
    fn: Callable
    risco: str = "leitura"  # um dos NIVEIS; sem declarar = leitura. Quem decide é o gate
    timeout: float = 25.0
    check: Optional[Callable[[], Tuple[bool, str]]] = None
    # Lê dado de terceiros (emails, agenda, páginas): depois dela a sessão fica "contaminada" e
    # passos de nível 2 ou mais exigem confirmação (regra 4 do CLAUDE.md).
    le_dado_externo: bool = False
    # Texto exato mostrado na confirmação (níveis 2 e 3). Sem ele, o gate descreve pelos parâmetros.
    confirmacao: Optional[Callable[[Dict[str, Any]], str]] = None
    # O que a ferramenta toca SEM aparecer nos parâmetros (a pasta onde um comando nomeado roda, por
    # exemplo). Devolve params "implícitos" que o contrato confere junto com os explícitos, com a mesma
    # convenção de nomes (pasta, url...). Pode levantar ToolError (ex.: comando fora do catálogo).
    alvos: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    # Só roda dentro de uma tarefa com contrato (o gate recusa fora dela) e não é oferecida ao roteador
    # de voz/LLM. É o caso das capacidades da Fase 3: o contrato é o que limita pastas e domínios.
    somente_tarefa: bool = False
    # O contrário: o gate RECUSA quando há contrato (tarefa agendada ou manual). É o caso de gmail.enviar:
    # envio só acontece por clique seu, nunca por uma tarefa, mesmo que o contrato liste a ferramenta.
    nunca_em_tarefa: bool = False

    def disponivel(self) -> Tuple[bool, str]:
        return self.check() if self.check else (True, "")

    def spec(self) -> Dict[str, Any]:
        ok, motivo = self.disponivel()
        return {
            "nome": self.name,
            "rotulo": self.rotulo,
            "descricao": self.descricao,
            "risco": self.risco,
            "nivel": nivel_de(self.risco),
            "somente_tarefa": self.somente_tarefa,
            "nunca_em_tarefa": self.nunca_em_tarefa,
            "disponivel": ok,
            "motivo": motivo,
            "params": [
                {"nome": p.name, "tipo": p.tipo, "default": p.default, "descricao": p.descricao,
                 "minimo": p.minimo, "maximo": p.maximo}
                for p in self.params
            ],
        }


REGISTRY: Dict[str, Tool] = {}


def tool(name, rotulo, descricao, params=(), risco="leitura", timeout=25.0, check=None,
         le_dado_externo=False, confirmacao=None, alvos=None, somente_tarefa=False, nunca_em_tarefa=False):
    if risco not in NIVEIS:
        raise ValueError(f"Ferramenta {name}: risco desconhecido {risco!r} (use um de {sorted(NIVEIS)})")

    def deco(fn):
        REGISTRY[name] = Tool(name, rotulo, descricao, list(params), fn, risco, timeout, check,
                              le_dado_externo, confirmacao, alvos, somente_tarefa, nunca_em_tarefa)
        return fn

    return deco


def catalog(only_available: bool = False, leitura_only: bool = False) -> List[Dict[str, Any]]:
    specs = [t.spec() for t in REGISTRY.values() if not leitura_only or t.risco == "leitura"]
    return [s for s in specs if s["disponivel"]] if only_available else specs


def coerce_params(t: Tool, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = raw or {}
    out: Dict[str, Any] = {}
    for p in t.params:
        v = raw.get(p.name, p.default)
        if v is None:
            out[p.name] = None
            continue
        try:
            if p.tipo == "int":
                v = int(v)
            elif p.tipo == "float":
                v = float(v)
            elif p.tipo == "bool":
                v = v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "sim", "yes")
            else:
                v = str(v)
        except (TypeError, ValueError) as exc:
            raise ToolError(f"Parâmetro inválido em {t.name}: {p.name}") from exc
        if p.tipo in ("int", "float"):
            if p.minimo is not None:
                v = max(v, type(v)(p.minimo))
            if p.maximo is not None:
                v = min(v, type(v)(p.maximo))
        out[p.name] = v
    return out
