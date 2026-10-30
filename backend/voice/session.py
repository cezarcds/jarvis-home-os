"""Máquina de estados da voz: espera a palavra "Jarvis", depois entrega o comando já transcrito.

Não conhece WebSocket nem Whisper (recebe funções), então é testável com áudio sintético.
Estados: idle (só ouvindo o nome) -> awake (esperando o comando) -> idle.
"""
import logging
import time
from typing import Awaitable, Callable, Dict, Optional

import numpy as np

from .segmenter import Segmenter, Utterance
from .wake import clean_text, find_wake

log = logging.getLogger("jarvis.voice")

Transcribe = Callable[[np.ndarray, str], Awaitable[str]]
Send = Callable[[Dict], Awaitable[None]]


class VoiceSession:
    def __init__(self, transcribe: Transcribe, send: Send, wake_word: str = "jarvis", awake_seconds: float = 8.0,
                 prompt: str = "", clock: Callable[[], float] = time.monotonic,
                 segmenter: Optional[Segmenter] = None):
        self.transcribe = transcribe
        self.send = send
        self.wake_word = wake_word
        self.awake_seconds = awake_seconds
        self.prompt = prompt
        self.clock = clock
        self.seg = segmenter or Segmenter()
        self.state = "idle"
        self.awake_until = 0.0
        self.muted = False

    # ----- áudio -----
    async def feed(self, pcm: bytes) -> None:
        if self.muted:
            return
        # A janela de "estou ouvindo o comando" não fecha no meio de uma frase.
        if self.state == "awake" and self.clock() >= self.awake_until and not self.seg.in_speech:
            self.state = "idle"
            await self.send({"type": "sleep"})
        for utt in self.seg.feed(pcm):
            await self._handle(utt)

    async def _handle(self, utt: Utterance) -> None:
        text = clean_text(await self.transcribe(utt.audio, self.prompt))
        if not text:
            return
        m = find_wake(text, self.wake_word)
        if self.state == "awake":
            if m and not m.command:  # chamou de novo: continua esperando o comando
                self._wake()
                await self.send({"type": "wake", "awake_seconds": self.awake_seconds})
                return
            await self._command(m.command if m else text)
            return
        if not m:
            log.debug("Ouvi (sem palavra de ativação): %r", text[:80])
            return
        await self.send({"type": "wake", "awake_seconds": self.awake_seconds})
        if m.command:
            await self._command(m.command)
        else:
            self._wake()

    def _wake(self, seconds: Optional[float] = None) -> None:
        self.state = "awake"
        self.awake_until = self.clock() + (seconds if seconds is not None else self.awake_seconds)

    async def _command(self, text: str) -> None:
        self.state = "idle"
        self.awake_until = 0.0
        await self.send({"type": "transcript", "text": text})

    # ----- controle vindo do navegador -----
    async def control(self, msg: Dict) -> None:
        kind = msg.get("type")
        if kind == "mute":
            self.muted = bool(msg.get("value"))
            self.seg.reset()  # descarta meia frase captada junto com a voz do próprio Jarvis
        elif kind == "follow_up":  # depois que o Jarvis fala, dá alguns segundos para a resposta sem chamar o nome
            try:
                secs = float(msg.get("seconds", self.awake_seconds))
            except (TypeError, ValueError):
                secs = self.awake_seconds
            self._wake(min(max(secs, 1.0), 30.0))
            await self.send({"type": "awake", "seconds": secs})
        elif kind == "sleep":
            self.state = "idle"
            self.awake_until = 0.0
            self.seg.reset()
        elif kind == "ping":
            await self.send({"type": "pong"})
