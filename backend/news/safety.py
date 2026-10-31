"""Proteção contra SSRF: o Jarvis só abre URLs públicas (http/https).
Os links vêm da busca do modelo, então nunca confiamos neles às cegas."""
from __future__ import annotations
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


def is_public_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


async def is_public_http_url_async(url: str) -> bool:
    return await asyncio.to_thread(is_public_http_url, url)
