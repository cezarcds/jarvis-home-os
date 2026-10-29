"""Criptografia dos segredos em repouso (Fernet).

A chave fica em ~/.jarvis/secret.key (permissão 600) ou em JARVIS_SECRET_KEY.
Isso protege contra commit/backup acidental do banco; não protege contra um
programa malicioso rodando como o seu usuário (ele leria a chave também).
"""
import os

from cryptography.fernet import Fernet, InvalidToken

from .config import data_dir

KEY_FILE = "secret.key"


class DecryptError(Exception):
    pass


def _load_key() -> bytes:
    env = os.getenv("JARVIS_SECRET_KEY", "").strip()
    if env:
        return env.encode()
    path = data_dir() / KEY_FILE
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


def encrypt(text: str) -> str:
    return Fernet(_load_key()).encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return Fernet(_load_key()).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptError("Não foi possível descriptografar (chave diferente da usada ao gravar).") from exc
