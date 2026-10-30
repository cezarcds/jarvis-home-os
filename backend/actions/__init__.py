"""Ações locais do JARVIS: abrir programas, organizar janelas e ver a tela.

Tudo aqui roda na máquina do usuário (o backend precisa estar na sessão do Windows,
não como serviço, para enxergar a área de trabalho).
"""


class ActionError(Exception):
    """Erro esperado, com mensagem amigável (pode ser falada em voz alta)."""
