"""Ferramentas da Fase 3: comando.rodar, vscode.abrir_projeto, navegador.abrir.

Todas são nível 1 (ação local) e só rodam pelo gate. Nenhuma aceita texto livre que vire comando:
o que roda vem do catálogo (comandos.json), o que abre vem de uma pasta cadastrada, e o navegador
só chega a domínios permitidos (escopo.dominios do contrato). Todas são `somente_tarefa`: o gate recusa
fora de uma tarefa com contrato.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from actions import gate
from actions.redact import redigir_saida
from routines.tools.registry import Param, ToolError, tool

from . import catalogo, navegador, processos

_CHARS_PERIGOSOS = re.compile(r'[&|<>^%"\r\n`]')  # .cmd no Windows passa por cmd.exe: nada disso entra


def _resultado(titulo: str, dados: Dict[str, Any], falado: str, resumo: str = "") -> Dict[str, Any]:
    return {"type": "acao", "title": titulo, "data": dados, "falado": falado, "resumo_llm": resumo or falado}


# ---- comando.rodar ---------------------------------------------------------------------------------

def _argv_do_comando(nome: str, quantidade: Any) -> Tuple[catalogo.Comando, List[str]]:
    c = catalogo.comando(nome)
    valores: Dict[str, str] = {}
    if quantidade is not None and "quantidade" not in c.params:
        raise ToolError(f"O comando «{nome}» não aceita «quantidade».")
    for k, spec in c.params.items():
        v = quantidade if quantidade is not None else spec.get("default")
        if v is None:
            raise ToolError(f"O comando «{nome}» precisa de «{k}».")
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ToolError(f"«{k}» precisa ser um número inteiro.") from None
        if not spec["min"] <= v <= spec["max"]:
            raise ToolError(f"«{k}» precisa ficar entre {spec['min']} e {spec['max']} (veio {v}).")
        valores[k] = str(v)
    argv = [catalogo.PLACEHOLDER.sub(lambda m: valores[m.group(1)], a) for a in c.exec]
    return c, argv


def _alvos_comando(params: Dict[str, Any]) -> Dict[str, Any]:
    c = catalogo.comando(params.get("nome"))
    return {"pasta": c.pasta}  # o contrato confere onde o comando vai rodar


def _confirma_comando(params: Dict[str, Any]) -> str:
    return f"Rodar o comando «{params.get('nome')}»."


@tool("comando.rodar", "rodar comando cadastrado",
      "Roda um comando NOMEADO do catálogo (~/.jarvis/comandos.json) na pasta do projeto dele. "
      "Nunca aceita texto livre: só o nome e, se o catálogo previr, a quantidade.",
      params=[Param("nome", "str", None, "nome do comando no catálogo"),
              Param("quantidade", "int", None, "quantidade, se o comando aceitar")],
      risco="acao_local", timeout=4 * 3600 + 30.0, confirmacao=_confirma_comando, alvos=_alvos_comando,
      somente_tarefa=True)
async def comando_rodar(nome=None, quantidade=None):
    c, argv = _argv_do_comando(nome, quantidade)  # revalida: não confia que o gate já olhou o catálogo
    if shutil.which(argv[0]) is None and not Path(argv[0]).exists():
        raise ToolError(f"O programa «{argv[0]}» do comando «{nome}» não foi encontrado.")
    try:
        codigo, saida, estourou = await processos.rodar(argv, c.pasta, c.timeout_s)
    except OSError as exc:
        raise ToolError(f"Não consegui iniciar «{nome}»: {exc.strerror or exc}") from exc
    saida = redigir_saida(saida)
    if estourou:
        raise ToolError(f"O comando «{nome}» passou de {c.timeout_s}s e foi encerrado.")
    if codigo != 0:
        fim = saida.strip().splitlines()[-3:]
        raise ToolError(f"O comando «{nome}» terminou com erro (código {codigo}). {' | '.join(fim)}"[:500])
    return _resultado("Comando", {"nome": nome, "codigo": codigo, "saida": saida, "pasta": c.pasta},
                      f"Comando {nome} concluído.", f"O comando {nome} terminou sem erro.")


# ---- vscode.abrir_projeto --------------------------------------------------------------------------

def _achar_vscode(cat: catalogo.Catalogo) -> str:
    if cat.vscode and Path(cat.vscode).exists():
        return cat.vscode
    achado = shutil.which("code")
    if not achado:
        raise ToolError("Não achei o VS Code (comando «code»). Cadastre \"vscode\" no catálogo.")
    return achado


@tool("vscode.abrir_projeto", "abrir projeto no VS Code",
      "Abre no VS Code uma pasta de projeto cadastrada no catálogo (~/.jarvis/comandos.json).",
      params=[Param("pasta", "str", None, "caminho completo da pasta do projeto")],
      risco="acao_local", timeout=30.0, somente_tarefa=True)
async def vscode_abrir_projeto(pasta=None):
    cat = catalogo.carregar()
    real = catalogo.projeto_por_pasta(pasta or "")
    if real is None or not pasta or _CHARS_PERIGOSOS.search(real):
        raise ToolError("Essa pasta não está entre os projetos cadastrados.")
    if not Path(real).is_dir():
        raise ToolError("A pasta do projeto não existe.")
    exe = _achar_vscode(cat)
    codigo, saida, estourou = await processos.rodar([exe, real], real, 20)
    if estourou or codigo != 0:
        raise ToolError(f"O VS Code não abriu o projeto (código {codigo}).")
    nome = Path(real).name
    return _resultado("VS Code", {"pasta": real}, f"Projeto {nome} aberto no VS Code.")


# ---- navegador.abrir -------------------------------------------------------------------------------

def _disponivel_navegador() -> Tuple[bool, str]:
    return navegador.disponivel()


def _dominios_permitidos() -> List[str]:
    contrato = gate.contrato_atual()
    if contrato is None:  # o gate já recusa fora de tarefa; isto é a segunda trava
        raise ToolError("O navegador só abre páginas dentro de uma tarefa com contrato.")
    return list(contrato.c.escopo.dominios)


@tool("navegador.abrir", "abrir página no navegador",
      "Abre uma página num navegador próprio (perfil separado do seu) e devolve título e texto. "
      "Só domínios permitidos; qualquer pedido de rede para fora da lista é bloqueado.",
      params=[Param("url", "str", None, "endereço http(s) completo")],
      risco="acao_local", timeout=60.0, le_dado_externo=True, check=_disponivel_navegador,
      somente_tarefa=True)
async def navegador_abrir(url=None):
    permitidos = _dominios_permitidos()
    return await navegador.abrir(url or "", permitidos)
