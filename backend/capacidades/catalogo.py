"""Catálogo de comandos e projetos permitidos: ~/.jarvis/comandos.json (fora do Git, só você edita).

Formato (schema 1):
{
  "schema": 1,
  "projetos": {"projeto-x": "C:/projetos/projeto-x"},
  "comandos": {
    "gerar_videos": {
      "exec": ["python", "gerar.py", "--quantidade", "{quantidade}"],
      "projeto": "projeto-x",
      "params": {"quantidade": {"min": 1, "max": 20, "default": 5}},
      "timeout_s": 1800
    }
  }
}

Regras (CLAUDE.md, regra 1): o Jarvis nunca monta comando. `exec` é uma lista fixa de argumentos (sem shell);
só `{quantidade}` — um inteiro validado pelo catálogo — é substituído, sempre como UM argumento.
O programa precisa ser um nome simples (resolvido no PATH) ou um caminho absoluto; o diretório de
trabalho é sempre um projeto cadastrado. O arquivo é lido a cada uso: editar vale na hora.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from connections.config import data_dir
from routines.tools.registry import ToolError

SCHEMA = 1
NOME_OK = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
PARAMS_SUPORTADOS = ("quantidade",)  # os parâmetros que a ferramenta comando.rodar sabe receber
TIMEOUT_MAX_S = 4 * 3600


@dataclass
class Comando:
    nome: str
    exec: List[str]
    projeto: str
    pasta: str
    params: Dict[str, dict] = field(default_factory=dict)
    timeout_s: int = 600


@dataclass
class Catalogo:
    projetos: Dict[str, str]
    comandos: Dict[str, Comando]
    vscode: Optional[str] = None                       # caminho absoluto do code(.cmd), se não estiver no PATH


def caminho() -> Path:
    return data_dir() / "comandos.json"


def _vazio() -> Catalogo:
    return Catalogo({}, {})


def carregar() -> Catalogo:
    """Lê e valida o arquivo. Arquivo ausente = catálogo vazio (nada permitido). Arquivo com erro
    levanta ToolError (falha fechada, com a mensagem do que corrigir)."""
    arq = caminho()
    if not arq.exists():
        return _vazio()
    try:
        bruto = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"O catálogo de comandos ({arq.name}) está ilegível: {exc}") from exc
    if not isinstance(bruto, dict) or bruto.get("schema") != SCHEMA:
        raise ToolError(f"O catálogo de comandos precisa de \"schema\": {SCHEMA}.")

    projetos: Dict[str, str] = {}
    for nome, pasta in (bruto.get("projetos") or {}).items():
        if not NOME_OK.match(str(nome)):
            raise ToolError(f"Nome de projeto inválido no catálogo: {nome!r}.")
        p = Path(str(pasta))
        if not p.is_absolute():
            raise ToolError(f"O projeto «{nome}» precisa de caminho absoluto.")
        projetos[nome] = os.path.realpath(p)

    comandos: Dict[str, Comando] = {}
    for nome, c in (bruto.get("comandos") or {}).items():
        if not NOME_OK.match(str(nome)):
            raise ToolError(f"Nome de comando inválido no catálogo: {nome!r}.")
        args = c.get("exec")
        if not isinstance(args, list) or not args or not all(isinstance(a, str) and a for a in args):
            raise ToolError(f"Comando «{nome}»: \"exec\" precisa ser uma lista de textos (sem shell).")
        prog = args[0]
        if (os.sep in prog or "/" in prog) and not Path(prog).is_absolute():
            raise ToolError(f"Comando «{nome}»: o programa é um nome simples ou um caminho absoluto.")
        projeto = c.get("projeto")
        if projeto not in projetos:
            raise ToolError(f"Comando «{nome}»: o projeto «{projeto}» não está cadastrado.")
        params = c.get("params") or {}
        for ph in {m for a in args for m in PLACEHOLDER.findall(a)}:
            if ph not in params or ph not in PARAMS_SUPORTADOS:
                raise ToolError(f"Comando «{nome}»: {{{ph}}} não é um parâmetro cadastrado e suportado.")
        for k, spec in params.items():
            if k not in PARAMS_SUPORTADOS or not isinstance(spec, dict):
                raise ToolError(f"Comando «{nome}»: parâmetro «{k}» não é suportado.")
            if not all(isinstance(spec.get(x), int) for x in ("min", "max")) or spec["min"] > spec["max"]:
                raise ToolError(f"Comando «{nome}»: «{k}» precisa de min e max inteiros.")
        timeout = c.get("timeout_s", 600)
        if not isinstance(timeout, int) or not 1 <= timeout <= TIMEOUT_MAX_S:
            raise ToolError(f"Comando «{nome}»: timeout_s deve ficar entre 1 e {TIMEOUT_MAX_S}.")
        comandos[nome] = Comando(nome, args, projeto, projetos[projeto], params, timeout)
    vscode = bruto.get("vscode")
    if vscode is not None and (not isinstance(vscode, str) or not Path(vscode).is_absolute()):
        raise ToolError("\"vscode\" precisa ser um caminho absoluto.")
    return Catalogo(projetos, comandos, vscode)


def comando(nome: Optional[str]) -> Comando:
    cat = carregar()
    c = cat.comandos.get(nome or "")
    if c is None:
        raise ToolError(f"«{nome}» não está no catálogo de comandos.")
    return c


def projeto_por_pasta(pasta: str) -> Optional[str]:
    """Pasta real do projeto cadastrado que é exatamente `pasta` (caminho completo; o NOME do projeto
    não vale, porque o contrato só entende caminhos). Subpasta ou pasta-mãe não valem."""
    if not pasta or not Path(pasta).is_absolute():
        return None
    cat = carregar()
    alvo = os.path.normcase(os.path.realpath(pasta))
    for p in cat.projetos.values():
        if os.path.normcase(p) == alvo:
            return p
    return None
