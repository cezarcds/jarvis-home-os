"""Transcrição local com faster-whisper (CTranslate2). O modelo é baixado na primeira execução."""
import importlib.util
import logging
import os
import threading
from typing import Optional, Tuple

import numpy as np

log = logging.getLogger("jarvis.stt")

_PROMPT = (
    "Jarvis. Abre o Profit. Abre o VS Code. Abre o Chrome. Olha a tela. Organiza a tela. "
    "Analisa o gráfico comigo. Bom dia, Jarvis."
)


def available() -> Tuple[bool, str]:
    if importlib.util.find_spec("faster_whisper") is None:
        return False, "Falta instalar o faster-whisper (pip install faster-whisper)."
    return True, ""


def model_name() -> str:
    return os.getenv("JARVIS_WHISPER_MODEL", "small").strip() or "small"


def prompt_hint() -> str:
    """Dica para o Whisper acertar 'Jarvis' e os nomes dos seus programas."""
    try:
        from actions.apps import load_catalog

        nomes = [e.falado for e in load_catalog()][:10]
        return "Jarvis. " + " ".join(f"Abre o {n}." for n in nomes) + " Olha a tela. Organiza a tela."
    except Exception:  # noqa: BLE001
        return _PROMPT


class WhisperTranscriber:
    def __init__(self, size: Optional[str] = None, device: Optional[str] = None, compute: Optional[str] = None):
        self.size = size or model_name()
        self.device = device or os.getenv("JARVIS_WHISPER_DEVICE", "auto")
        self.compute = compute or os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
        self._model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            log.info("Carregando Whisper '%s' (device=%s, compute=%s)...", self.size, self.device, self.compute)
            self._model = WhisperModel(self.size, device=self.device, compute_type=self.compute)
            log.info("Whisper pronto.")

    def transcribe(self, audio: np.ndarray, prompt: str = "") -> str:
        self.load()
        with self._lock:
            segments, _info = self._model.transcribe(
                audio,
                language="pt",
                beam_size=1,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
                initial_prompt=prompt or None,
                no_speech_threshold=0.6,
                temperature=0.0,
            )
            parts = [s.text.strip() for s in segments if getattr(s, "no_speech_prob", 0.0) < 0.8]
        return " ".join(p for p in parts if p).strip()


_singleton: Optional[WhisperTranscriber] = None


def get_transcriber() -> WhisperTranscriber:
    global _singleton
    if _singleton is None:
        _singleton = WhisperTranscriber()
    return _singleton
