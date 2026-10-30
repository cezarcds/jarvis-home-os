"""Detector de fala por energia (VAD simples, só numpy): corta o áudio em frases.

Usa um piso de ruído adaptativo, então funciona em salas com ruído de fundo diferente.
O Whisper ainda aplica o próprio filtro de silêncio dentro de cada trecho.
"""
from collections import deque
from dataclasses import dataclass
from typing import Deque, List

import numpy as np

SAMPLE_RATE = 16000


@dataclass
class Utterance:
    audio: np.ndarray  # float32, mono, 16 kHz, -1..1

    @property
    def duration(self) -> float:
        return len(self.audio) / SAMPLE_RATE


class Segmenter:
    def __init__(
        self,
        frame_ms: int = 30,
        min_speech_ms: int = 250,
        end_silence_ms: int = 700,
        max_utterance_s: float = 15.0,
        preroll_ms: int = 300,
        start_frames: int = 3,
        min_threshold: float = 0.012,
        threshold_factor: float = 3.0,
    ):
        self.frame_ms = frame_ms
        self.frame = SAMPLE_RATE * frame_ms // 1000
        self.min_speech_ms = min_speech_ms
        self.end_silence_ms = end_silence_ms
        self.max_frames = int(max_utterance_s * 1000 / frame_ms)
        self.start_frames = start_frames
        self.min_threshold = min_threshold
        self.factor = threshold_factor
        self._preroll: Deque[np.ndarray] = deque(maxlen=max(1, preroll_ms // frame_ms))
        self.reset()

    def reset(self) -> None:
        self._rest = np.zeros(0, dtype=np.int16)
        self._noise = 0.004
        self._in_speech = False
        self._run = 0
        self._silence_ms = 0
        self._speech_ms = 0
        self._buf: List[np.ndarray] = []
        self._preroll.clear()

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def feed(self, pcm: bytes) -> List[Utterance]:
        """Recebe PCM16 little-endian 16 kHz mono. Devolve as frases que terminaram neste pedaço."""
        if len(pcm) % 2:
            pcm = pcm[:-1]
        data = np.frombuffer(pcm, dtype="<i2")
        x = np.concatenate([self._rest, data]) if self._rest.size else data
        n = len(x) // self.frame
        self._rest = x[n * self.frame:].copy()
        out: List[Utterance] = []
        for i in range(n):
            u = self._step(x[i * self.frame:(i + 1) * self.frame])
            if u is not None:
                out.append(u)
        return out

    def _finish(self):
        audio = np.concatenate(self._buf).astype(np.float32) / 32768.0 if self._buf else np.zeros(0, np.float32)
        ok = self._speech_ms >= self.min_speech_ms
        self._in_speech = False
        self._run = 0
        self._silence_ms = 0
        self._speech_ms = 0
        self._buf = []
        self._preroll.clear()
        return Utterance(audio) if ok else None

    def _step(self, frame: np.ndarray):
        f = frame.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(f * f))) if f.size else 0.0
        thr = max(self.min_threshold, self._noise * self.factor)

        if not self._in_speech:
            self._preroll.append(frame)
            if rms > thr:
                self._run += 1
                if self._run >= self.start_frames:
                    self._in_speech = True
                    self._buf = list(self._preroll)
                    self._speech_ms = self._run * self.frame_ms
                    self._silence_ms = 0
            else:
                self._run = 0
                self._noise = min(0.03, 0.95 * self._noise + 0.05 * rms)
            return None

        self._buf.append(frame)
        if rms > thr * 0.7:  # histerese: dentro da fala, tolera quedas de volume
            self._silence_ms = 0
            self._speech_ms += self.frame_ms
        else:
            self._silence_ms += self.frame_ms
        if self._silence_ms >= self.end_silence_ms or len(self._buf) >= self.max_frames:
            return self._finish()
        return None
