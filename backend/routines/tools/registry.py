"""Catálogo de ferramentas que as rotinas podem usar.

Uma ferramenta é uma função assíncrona que devolve um dict:
  {"type": "agenda|emails|clima|metricas|...", "title": str, "data": {...},
   "falado": "frase para o modo template", "resumo_llm": "texto curto para o resumo por LLM"}
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


class ToolError(Exception):
    """Erro esperado, com mensagem amigável."""


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
    risco: str = "leitura"  # leitura | acao_local (abrir programas, janelas); rotinas só executam "leitura"
    timeout: float = 25.0
    check: Optional[Callable[[], Tuple[bool, str]]] = None

    def disponivel(self) -> Tuple[bool, str]:
        return self.check() if self.check else (True, "")

    def spec(self) -> Dict[str, Any]:
        ok, motivo = self.disponivel()
        return {
            "nome": self.name,
            "rotulo": self.rotulo,
            "descricao": self.descricao,
            "risco": self.risco,
            "disponivel": ok,
            "motivo": motivo,
            "params": [
                {"nome": p.name, "tipo": p.tipo, "default": p.default, "descricao": p.descricao,
                 "minimo": p.minimo, "maximo": p.maximo}
                for p in self.params
            ],
        }


REGISTRY: Dict[str, Tool] = {}


def tool(name, rotulo, descricao, params=(), risco="leitura", timeout=25.0, check=None):
    def deco(fn):
        REGISTRY[name] = Tool(name, rotulo, descricao, list(params), fn, risco, timeout, check)
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
