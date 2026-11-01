"""Registra as ações no catálogo de ferramentas (risco 'acao_local').

Quem executa estas funções é o gate (actions/gate.py); ninguém as chama direto. O motor de
rotinas só deixa passar nível 0, então rotinas salvas nunca as acionam.
"""
from typing import Tuple

from routines.tools.registry import Param, tool

from . import config


def _check() -> Tuple[bool, str]:
    if not config.actions_enabled():
        return False, "Ações desligadas (JARVIS_ACTIONS_ENABLED=0)"
    from . import handler

    if not handler.win.AVAILABLE:  # handler.win é trocável nos testes (e é o que as ações usam)
        return False, "Disponível só no Windows"
    return True, ""


async def _run(name: str, params: dict) -> dict:
    from . import gate, handler

    # A sessão vem do contexto do gate (setada em executar), não de um "tool" fixo.
    r = await handler._executar_acao(name, params, gate.sessao_atual())
    texto = r["text"] if r else ""  # r é None quando não era um pedido de abrir programa
    return {"type": "acao", "title": "Ação", "data": {"mensagem": texto}, "falado": texto,
            "resumo_llm": texto, "resposta": r}


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
