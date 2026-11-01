"""YouTube: enviar vídeo SOMENTE como privado (Fase 4).

A trava de privacidade é do CÓDIGO, não do contrato nem do Google (a documentação atual deixa de forçar
privado para projetos não verificados): a ferramenta não tem parâmetro de visibilidade, o corpo da
requisição sempre leva privacyStatus=private e o retorno da API é conferido. Publicar fica fora desta fase.

Convenção do contrato: `arquivo` precisa estar dentro de escopo.pastas e `conta` em escopo.contas.
`conta` é o RÓTULO que você deu à conta no contrato; o token do Google é um só e define o canal real.
"""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from typing import Any, Dict, List

from ..google_auth import GoogleAuthError, check_escopo, get_service
from .registry import Param, ToolError, tool

EXTENSOES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
TITULO_MAX = 100
DESCRICAO_MAX_BYTES = 5000
TAGS_MAX = 30
TAGS_TOTAL_MAX = 500
CHUNK = 8 * 1024 * 1024

_parar = threading.Event()  # gancho do botão PARAR: a thread do upload confere entre os blocos


def _ao_parar() -> None:
    _parar.set()


def _registrar_gancho() -> None:
    from actions import gate

    gate.registrar_gancho_parada(_ao_parar)


_gancho_ok = False


def _check():
    return check_escopo("youtube")


def validar(arquivo: str, titulo: str, descricao: str, tags: str) -> Dict[str, Any]:
    """Valida tudo ANTES de tocar na rede. Levanta ToolError com a mensagem do que corrigir."""
    if not arquivo:
        raise ToolError("Informe o arquivo do vídeo.")
    p = Path(arquivo)
    if not p.is_absolute():
        raise ToolError("O arquivo do vídeo precisa de caminho completo.")
    if p.suffix.lower() not in EXTENSOES:
        raise ToolError(f"Formato não aceito ({p.suffix or 'sem extensão'}). Aceitos: {', '.join(sorted(EXTENSOES))}.")
    if not p.is_file():
        raise ToolError("O arquivo do vídeo não existe.")
    if p.stat().st_size <= 0:
        raise ToolError("O arquivo do vídeo está vazio.")
    titulo = (titulo or "").strip()
    if not titulo or len(titulo) > TITULO_MAX or any(c in titulo for c in "<>\r\n"):
        raise ToolError(f"O título precisa ter de 1 a {TITULO_MAX} caracteres, em uma linha, sem < ou >.")
    descricao = (descricao or "").strip()
    if len(descricao.encode("utf-8")) > DESCRICAO_MAX_BYTES or "<" in descricao or ">" in descricao:
        raise ToolError(f"A descrição passa de {DESCRICAO_MAX_BYTES} bytes ou tem < ou >.")
    lista: List[str] = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if len(lista) > TAGS_TOTAL_MAX or len(lista) > TAGS_MAX or sum(len(t) for t in lista) > TAGS_TOTAL_MAX \
            or any("<" in t or ">" in t for t in lista):
        raise ToolError(f"Até {TAGS_MAX} tags, {TAGS_TOTAL_MAX} caracteres no total, sem < ou >.")
    return {"arquivo": str(p), "titulo": titulo, "descricao": descricao, "tags": lista}


def corpo_privado(v: Dict[str, Any]) -> Dict[str, Any]:
    """O corpo enviado ao Google. A visibilidade NÃO vem de parâmetro nenhum: é sempre private."""
    snippet: Dict[str, Any] = {"title": v["titulo"], "description": v["descricao"]}
    if v["tags"]:
        snippet["tags"] = v["tags"]
    return {"snippet": snippet, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}


def _enviar(v: Dict[str, Any]) -> Dict[str, Any]:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    svc = get_service("youtube", "v3", escopo="youtube")
    media = MediaFileUpload(v["arquivo"], chunksize=CHUNK, resumable=True)
    req = svc.videos().insert(part="snippet,status", body=corpo_privado(v), media_body=media)
    _parar.clear()
    resposta = None
    try:
        while resposta is None:
            if _parar.is_set():
                raise ToolError("Envio cancelado pelo botão PARAR antes de terminar.")
            _, resposta = req.next_chunk()
    except HttpError as exc:
        status = getattr(getattr(exc, "resp", None), "status", 0)
        texto = str(exc)[:200]
        if status in (400, 401, 403, 404):
            if "quota" in texto.lower():
                raise ToolError("A cota diária de envios do YouTube acabou.") from exc
            raise ToolError(f"O YouTube recusou o envio ({status}).") from exc
        raise  # 5xx/rede: não dá para saber se subiu -> o executor trata como "incerto"
    visib = ((resposta or {}).get("status") or {}).get("privacyStatus")
    if visib != "private":
        # Nunca deveria acontecer. Se acontecer, não esconde: avisa com o id para você corrigir no YouTube.
        raise ToolError(f"ATENÇÃO: o vídeo {resposta.get('id')} ficou «{visib}» no YouTube. Torne-o privado já.")
    return {"id": resposta["id"], "visibilidade": visib, "link": f"https://studio.youtube.com/video/{resposta['id']}/edit"}


def _confirma(params: Dict[str, Any]) -> str:
    return (f"Enviar o vídeo «{os.path.basename(str(params.get('arquivo')))}» ao YouTube como PRIVADO, "
            f"com o título «{params.get('titulo')}».")


@tool(
    "youtube.upload_privado", "enviar vídeo privado ao YouTube",
    "Envia um vídeo ao YouTube SEMPRE como privado (não há como publicar por aqui), com título, descrição e tags.",
    [Param("arquivo", "str", None, "caminho completo do vídeo"),
     Param("titulo", "str", None, "título (até 100 caracteres)"),
     Param("descricao", "str", "", "descrição (até 5000 bytes)"),
     Param("tags", "str", "", "tags separadas por vírgula"),
     Param("conta", "str", None, "rótulo da conta, como no contrato (ex.: youtube:canal-teste)")],
    risco="externo_reversivel", timeout=3 * 3600, check=_check, confirmacao=_confirma, somente_tarefa=True,
)
async def youtube_upload_privado(arquivo=None, titulo=None, descricao="", tags="", conta=None):
    global _gancho_ok
    if not _gancho_ok:
        _registrar_gancho()
        _gancho_ok = True
    v = validar(arquivo or "", titulo or "", descricao or "", tags or "")
    try:
        r = await asyncio.to_thread(_enviar, v)
    except GoogleAuthError as exc:
        raise ToolError(str(exc)) from exc
    falado = f"Vídeo «{v['titulo']}» enviado como privado."
    return {"type": "acao", "title": "YouTube", "data": {**r, "titulo": v["titulo"], "arquivo": v["arquivo"]},
            "falado": falado, "resumo_llm": falado}
