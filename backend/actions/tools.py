"""Registra as ações no catálogo de ferramentas (risco 'acao_local').

O motor de rotinas continua só executando ferramentas de leitura; estas são chamadas pelo
handler (comando direto ou escolha do LLM), nunca por rotinas salvas.
"""
from typing import Tuple

from routines.tools.registry import Param, tool

from . import config, winapi


def _check() -> Tuple[bool, str]:
    if not config.actions_enabled():
        return False, "Ações desligadas (JARVIS_ACTIONS_ENABLED=0)"
    if not winapi.AVAILABLE:
        return False, "Disponível só no Windows"
    return True, ""


async def _run(name: str, params: dict) -> dict:
    from . import handler

    r = await handler.run_tool(name, params, "tool")
    return {"type": "acao", "title": "Ação", "data": {"mensagem": r["text"]}, "falado": r["text"], "resumo_llm": r["text"]}


@tool("app.abrir", "abrir programa",
      "Abre um programa do computador e organiza a tela (programa em 2/3, Jarvis em 1/3). Ex.: Profit, VS Code, Chrome.",
      params=[Param("app", "str", None, "nome do programa, como o usuário falou"),
              Param("organizar", "bool", True, "organizar a tela ao abrir")],
      risco="acao_local", timeout=30.0, check=_check)
async def app_abrir(app, organizar=True):
    return await _run("app.abrir", {"app": app, "organizar": organizar})


@tool("tela.organizar", "organizar a tela",
      "Reaplica o layout (programa em foco em 2/3, Jarvis em 1/3) nas janelas abertas.",
      risco="acao_local", timeout=20.0, check=_check)
async def tela_organizar():
    return await _run("tela.organizar", {})


@tool("tela.restaurar_jarvis", "Jarvis em tela cheia",
      "Faz a janela do Jarvis voltar a ocupar a tela inteira.",
      risco="acao_local", timeout=20.0, check=_check)
async def tela_restaurar_jarvis():
    return await _run("tela.restaurar_jarvis", {})
