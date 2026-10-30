"""Configuração do módulo de conexões. Tudo é lido na hora do uso (não no import),
para que o .env carregado pelo main.py e os testes funcionem em qualquer ordem."""
import os
from pathlib import Path

DEFAULT_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",  # npm run dev
    "http://localhost:8000", "http://127.0.0.1:8000",  # HUD compilado, servido pelo backend
)


def _inside_git_repo(path: Path) -> bool:
    return any((p / ".git").exists() for p in [path, *path.parents])


def data_dir() -> Path:
    """Pasta do banco e da chave. Padrão ~/.jarvis, SEMPRE fora do repositório."""
    d = Path(os.getenv("JARVIS_DATA_DIR") or Path.home() / ".jarvis").expanduser().resolve()
    if _inside_git_repo(d):
        raise RuntimeError(
            f"JARVIS_DATA_DIR ({d}) está dentro de um repositório Git. "
            "Use uma pasta fora do projeto para não versionar tokens por acidente."
        )
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:  # Windows
        pass
    return d


def backend_url() -> str:
    return os.getenv("JARVIS_BACKEND_URL", "http://localhost:8000").rstrip("/")


def allowed_origins() -> list[str]:
    raw = os.getenv("JARVIS_ALLOWED_ORIGINS")
    if raw:
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return list(DEFAULT_ORIGINS)
