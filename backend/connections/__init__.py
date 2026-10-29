"""Conexões com contas externas (cofre de tokens, OAuth, admin e ferramentas).

Integração com o app (em backend/main.py):

    from connections import router as connections_router
    from connections.tools import run_tools_phase
    app.include_router(connections_router)
"""
from .routes import router
from .tools import ToolsOutcome, run_tools_phase, wrap_untrusted

__all__ = ["router", "run_tools_phase", "ToolsOutcome", "wrap_untrusted"]
