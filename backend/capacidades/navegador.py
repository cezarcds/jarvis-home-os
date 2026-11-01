"""Navegador do Jarvis (Playwright) com perfil PRÓPRIO e rede restrita a uma allowlist de domínios.

- Perfil em ~/.jarvis/browser-profile, separado do seu navegador pessoal (AGENTE.md, seção 8).
- TODA requisição da página (documento, imagem, script, cada salto de redirecionamento) passa por um
  filtro de rede: host fora da lista é abortado ANTES de sair da máquina. Depois de carregar, a URL final é conferida de novo.
- Só http/https; sem downloads; timeout curto; o texto devolvido é truncado e redigido.
- O botão PARAR fecha o navegador (gancho do gate), além do cancelamento normal da tarefa.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from actions import gate
from actions.redact import redigir_saida
from connections.config import data_dir
from routines.tools.registry import ToolError
from tarefas.contrato import dominio_ok

log = logging.getLogger("jarvis.navegador")

TIMEOUT_NAVEGACAO_MS = 20_000
TEXTO_MAX = 3000
MAX_SALTOS = 5
_ativos: List[Tuple[asyncio.AbstractEventLoop, Any]] = []
_trava = threading.Lock()
_ocupado = False
_gancho_registrado = False


def disponivel() -> Tuple[bool, str]:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, "Instale o Playwright (pip install playwright; playwright install chromium)"
    return True, ""


def perfil() -> str:
    p = data_dir() / "browser-profile"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def url_ok(url: str, permitidos: List[str]) -> Optional[str]:
    """None se a URL pode ser aberta; senão, o motivo (em português)."""
    try:
        u = urlparse(url)
    except ValueError:
        return "Endereço inválido."
    if u.scheme not in ("http", "https") or not u.hostname:
        return "Só endereços http e https são permitidos."
    if u.username or u.password:
        return "Endereço com usuário/senha não é permitido."
    if not permitidos:
        return "Nenhum domínio está permitido para o navegador."
    if not dominio_ok(url, permitidos):
        return f"O domínio «{u.hostname}» não está entre os permitidos."
    return None


def _fechar_tudo_do_gancho() -> None:
    """Gancho do botão PARAR: pode vir de outra thread; pede o fechamento no loop de cada navegador."""
    with _trava:
        ativos = list(_ativos)
    for loop, ctx in ativos:
        try:
            asyncio.run_coroutine_threadsafe(ctx.close(), loop)
        except Exception:  # noqa: BLE001 - o loop pode já ter acabado
            pass


async def abrir(url: str, permitidos: List[str]) -> Dict[str, Any]:
    global _ocupado, _gancho_registrado
    motivo = url_ok(url, permitidos)
    if motivo:
        raise ToolError(motivo)
    if _ocupado:
        raise ToolError("O navegador do Jarvis já está em uso.")
    from playwright.async_api import Error as PwError, async_playwright

    if not _gancho_registrado:
        gate.registrar_gancho_parada(_fechar_tudo_do_gancho)
        _gancho_registrado = True
    _ocupado = True
    bloqueados: List[str] = []
    try:
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(
                perfil(), headless=True, accept_downloads=False, service_workers="block",
                args=["--disable-extensions", "--no-first-run"])
            with _trava:
                _ativos.append((asyncio.get_running_loop(), ctx))
            try:
                final_doc: Dict[str, str] = {}

                async def filtro(route):
                    """Decide cada requisição. Redirecionamentos são resolvidos AQUI, salto a salto, porque o
                    Chromium segue 3xx por dentro da rede sem repassar o destino ao filtro."""
                    req = route.request
                    alvo = req.url
                    if alvo.startswith(("data:", "blob:", "about:")):
                        await route.continue_()
                        return
                    for _salto in range(MAX_SALTOS + 1):
                        if url_ok(alvo, permitidos) is not None:
                            bloqueados.append(urlparse(alvo).hostname or alvo[:40])
                            await route.abort("blockedbyclient")
                            return
                        try:
                            resp = await route.fetch(url=alvo, max_redirects=0)
                        except PwError:
                            await route.abort("failed")
                            return
                        destino = resp.headers.get("location")
                        if resp.status in (301, 302, 303, 307, 308) and destino:
                            alvo = urljoin(alvo, destino)
                            continue
                        if req.is_navigation_request() and req.frame == page_ref[0].main_frame:
                            final_doc["url"] = alvo
                        await route.fulfill(response=resp)
                        return
                    bloqueados.append("redirecionamentos demais")
                    await route.abort("failed")

                page_ref: List[Any] = []
                await ctx.route("**/*", filtro)
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                page_ref.append(page)
                page.set_default_timeout(TIMEOUT_NAVEGACAO_MS)
                try:
                    resp = await page.goto(url, wait_until="load", timeout=TIMEOUT_NAVEGACAO_MS)
                except PwError as exc:
                    if bloqueados:
                        raise ToolError(f"A página tentou sair da allowlist ({bloqueados[0]}); bloqueado.") from exc
                    raise ToolError(f"Não consegui abrir a página: {str(exc).splitlines()[0][:150]}") from exc
                final = final_doc.get("url") or page.url
                motivo = url_ok(final, permitidos)
                if motivo:
                    raise ToolError(f"A página terminou fora da allowlist: {motivo}")
                titulo = await page.title()
                texto = await page.evaluate("() => (document.body ? document.body.innerText : '')")
                status = resp.status if resp else None
            finally:
                with _trava:
                    _ativos[:] = [a for a in _ativos if a[1] is not ctx]
                await ctx.close()
    finally:
        _ocupado = False
    texto = redigir_saida(texto, TEXTO_MAX)
    return {"type": "pagina", "title": titulo or final,
            "data": {"url": final, "titulo": titulo, "status": status, "texto": texto, "bloqueados": sorted(set(bloqueados))},
            "falado": f"Abri {titulo or final}.", "resumo_llm": f"Página «{titulo}» ({final}): {texto[:600]}"}
