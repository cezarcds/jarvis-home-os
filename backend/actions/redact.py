"""Redação de parâmetros antes de gravar na auditoria (regra 5: segredo nunca em log).

Duas defesas: pelo NOME da chave (senha, token, secret...) e pelo FORMATO do valor
(Bearer ..., sequências longas que parecem chave). Também corta textos longos: a auditoria
guarda o que foi feito, não o conteúdo inteiro de um email.
"""
import re
from typing import Any

REDIGIDO = "[REDIGIDO]"
MAX_TEXTO = 200
MAX_ITENS = 20
MAX_PROFUNDIDADE = 4

_CHAVE_SENSIVEL = re.compile(
    r"(token|senha|password|passwd|secret|segredo|api[_-]?key|apikey|chave|authorization|cookie|credential|bearer|auth)",
    re.I,
)
_BEARER = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I)
_PARECE_CHAVE = re.compile(r"[A-Za-z0-9_\-]{32,}")


def _texto(v: str) -> str:
    v = _BEARER.sub(REDIGIDO, v)
    v = _PARECE_CHAVE.sub(REDIGIDO, v)
    if len(v) > MAX_TEXTO:
        v = f"{v[:MAX_TEXTO]}…(+{len(v) - MAX_TEXTO})"
    return v


def redigir(valor: Any, _nivel: int = 0) -> Any:
    """Cópia de `valor` pronta para a auditoria (só tipos simples: dict, list, str, números, bool, None)."""
    if _nivel > MAX_PROFUNDIDADE:
        return "[…]"
    if isinstance(valor, dict):
        out = {}
        for k, v in list(valor.items())[:MAX_ITENS]:
            chave = str(k)[:60]
            out[chave] = REDIGIDO if _CHAVE_SENSIVEL.search(chave) else redigir(v, _nivel + 1)
        return out
    if isinstance(valor, (list, tuple, set)):
        return [redigir(v, _nivel + 1) for v in list(valor)[:MAX_ITENS]]
    if isinstance(valor, str):
        return _texto(valor)
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    return _texto(str(valor))


def redigir_saida(texto: str, maximo: int = 1500) -> str:
    """Saída de comando/página: tira segredos pelo formato e guarda só o FIM (onde ficam os erros)."""
    texto = _PARECE_CHAVE.sub(REDIGIDO, _BEARER.sub(REDIGIDO, texto or ""))
    return texto if len(texto) <= maximo else "…" + texto[-maximo:]
