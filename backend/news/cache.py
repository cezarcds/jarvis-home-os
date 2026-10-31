from __future__ import annotations
import time


class TTLCache:
    """Cache em memória, simples, com validade e tamanho máximo."""

    def __init__(self, ttl: float = 600, maxsize: int = 256):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: dict = {}

    def get(self, key):
        hit = self._data.get(key)
        if not hit:
            return None
        expires, value = hit
        if expires < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key, value, ttl: float | None = None):
        if len(self._data) >= self.maxsize:
            # descarta o mais antigo a expirar
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)
        self._data[key] = (time.time() + (ttl if ttl is not None else self.ttl), value)
