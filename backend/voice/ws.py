"""WebSocket de voz: o navegador manda PCM16 16 kHz e recebe eventos JSON."""
import asyncio
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from actions.config import voice_enabled
from connections.config import allowed_origins, backend_url

from . import stt
from .session import VoiceSession

log = logging.getLogger("jarvis.voice")
router = APIRouter(prefix="/v1/voice")


def _wake_word() -> str:
    return (os.getenv("JARVIS_WAKE_WORD") or "jarvis").strip().lower()


def _origins() -> set:
    """Origens do HUD: as configuradas + o próprio backend (quando serve o HUD pronto)."""
    base = backend_url()
    extra = {base, base.replace("localhost", "127.0.0.1")}
    return {o.rstrip("/") for o in allowed_origins()} | extra


@router.get("/status")
async def status():
    ok, reason = stt.available()
    enabled = voice_enabled()
    return {
        "enabled": enabled,
        "available": bool(enabled and ok),
        "reason": "" if not enabled and ok else ("Voz desligada (JARVIS_VOICE_ENABLED=0)." if not enabled else reason),
        "model": stt.model_name(),
        "wake_word": _wake_word(),
        "loaded": stt.get_transcriber().loaded if ok else False,
    }


@router.websocket("/ws")
async def voice_ws(ws: WebSocket):
    # WebSocket não tem CORS: sem esta checagem, qualquer site aberto no navegador poderia usar o seu Jarvis.
    origin = (ws.headers.get("origin") or "").rstrip("/")
    if origin and origin not in _origins():
        await ws.close(code=4403)
        return
    await ws.accept()

    ok, reason = stt.available()
    if not voice_enabled() or not ok:
        await ws.send_json({"type": "error", "code": "unavailable",
                            "message": reason or "Voz desligada (JARVIS_VOICE_ENABLED=0)."})
        await ws.close()
        return

    tr = stt.get_transcriber()
    if not tr.loaded:
        await ws.send_json({"type": "loading", "model": tr.size})
        try:
            await asyncio.to_thread(tr.load)
        except Exception as exc:  # noqa: BLE001 - sem internet na 1ª vez, pouca memória, etc.
            log.exception("Falha ao carregar o Whisper")
            await ws.send_json({"type": "error", "code": "load_failed",
                                "message": f"Não consegui carregar o Whisper: {str(exc)[:160]}"})
            await ws.close()
            return

    async def transcribe(audio, prompt):
        return await asyncio.to_thread(tr.transcribe, audio, prompt)

    async def send(msg):
        try:
            await ws.send_json(msg)
        except Exception:  # noqa: BLE001 - socket já fechou
            pass

    session = VoiceSession(transcribe, send, wake_word=_wake_word(), prompt=stt.prompt_hint())
    await send({"type": "ready", "wake_word": session.wake_word, "model": tr.size})
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                await session.feed(msg["bytes"])
            elif msg.get("text"):
                try:
                    await session.control(json.loads(msg["text"]))
                except (json.JSONDecodeError, AttributeError):
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("Sessão de voz encerrada por erro")
