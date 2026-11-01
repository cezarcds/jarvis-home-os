from .registry import REGISTRY, Tool, ToolError, catalog, coerce_params  # noqa: F401

# Importar os módulos registra as ferramentas no catálogo.
from . import agenda, analytics, clima, gmail, gmail_escrita, youtube  # noqa: E402,F401
from actions import tools as _acoes  # noqa: E402,F401  (ações locais: abrir programas, janelas)
from capacidades import tools as _capacidades  # noqa: E402,F401  (Fase 3: comando nomeado, VS Code, navegador)
