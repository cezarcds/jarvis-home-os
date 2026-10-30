from .registry import REGISTRY, Tool, ToolError, catalog, coerce_params  # noqa: F401

# Importar os módulos registra as ferramentas no catálogo.
from . import agenda, analytics, clima, gmail  # noqa: E402,F401
from actions import tools as _acoes  # noqa: E402,F401  (ações locais: abrir programas, janelas)
