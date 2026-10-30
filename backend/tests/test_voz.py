"""Sessão de voz (palavra de ativação + comando) e o WebSocket, com Whisper simulado."""
import asyncio
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice import stt
from voice.segmenter import SAMPLE_RATE
from voice.session import VoiceSession


def tone(seconds, amp=0.3):
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * t) * amp * 32767).astype("<i2")


def silence(seconds):
    return np.zeros(int(SAMPLE_RATE * seconds), dtype="<i2")


def frase(texto_ouvido=None):
    """1 s de 'fala' seguida de 1,2 s de silêncio (o suficiente para o segmentador fechar a frase)."""
    return np.concatenate([tone(1.0), silence(1.2)]).tobytes()


class Palco:
    """Sessão com relógio e transcrição controlados."""

    def __init__(self, falas):
        self.falas = list(falas)
        self.eventos = []
        self.t = 100.0

        async def transcribe(audio, prompt):
            return self.falas.pop(0) if self.falas else ""

        async def send(msg):
            self.eventos.append(msg)

        self.s = VoiceSession(transcribe, send, clock=lambda: self.t)

    def tipos(self):
        return [e["type"] for e in self.eventos]


def rodar(coro):
    return asyncio.run(coro)


def test_sem_palavra_de_ativacao_ignora_a_conversa_ao_redor():
    p = Palco(["que dia lindo hoje"])
    rodar(p.s.feed(frase()))
    assert p.eventos == [] and p.s.state == "idle"


def test_jarvis_com_comando_na_mesma_frase():
    p = Palco(["Jarvis, abre o Profit"])
    rodar(p.s.feed(frase()))
    assert p.eventos == [{"type": "wake", "awake_seconds": 8.0}, {"type": "transcript", "text": "abre o Profit"}]
    assert p.s.state == "idle"


def test_jarvis_sozinho_espera_o_comando_na_frase_seguinte():
    p = Palco(["Jarvis", "olha minha tela"])

    async def tudo():
        await p.s.feed(frase())
        assert p.s.state == "awake"
        await p.s.feed(frase())

    rodar(tudo())
    assert p.tipos() == ["wake", "transcript"]
    assert p.eventos[-1]["text"] == "olha minha tela"


def test_janela_de_comando_expira_e_avisa():
    p = Palco(["Jarvis"])

    async def tudo():
        await p.s.feed(frase())
        p.t += 9
        await p.s.feed(silence(0.1).tobytes())

    rodar(tudo())
    assert p.tipos() == ["wake", "sleep"] and p.s.state == "idle"


def test_depois_de_expirar_a_fala_solta_nao_vira_comando():
    p = Palco(["Jarvis", "abre o profit"])

    async def tudo():
        await p.s.feed(frase())
        p.t += 9
        await p.s.feed(frase())

    rodar(tudo())
    assert "transcript" not in p.tipos()


def test_follow_up_dispensa_dizer_jarvis_de_novo():
    p = Palco(["e o volume?"])

    async def tudo():
        await p.s.control({"type": "follow_up", "seconds": 8})
        await p.s.feed(frase())

    rodar(tudo())
    assert p.eventos[-1] == {"type": "transcript", "text": "e o volume?"}


def test_mudo_ignora_audio_e_descarta_o_que_estava_sendo_captado():
    p = Palco(["Jarvis abre o profit"])

    async def tudo():
        await p.s.control({"type": "mute", "value": True})
        await p.s.feed(frase())
        await p.s.control({"type": "mute", "value": False})

    rodar(tudo())
    assert p.eventos == []


def test_lixo_do_whisper_e_ignorado():
    p = Palco(["Legendas pela comunidade Amara.org"])
    rodar(p.s.feed(frase()))
    assert p.eventos == []


def test_sleep_manual_volta_para_idle():
    p = Palco(["Jarvis"])

    async def tudo():
        await p.s.feed(frase())
        await p.s.control({"type": "sleep"})

    rodar(tudo())
    assert p.s.state == "idle"


# ---------- WebSocket ----------
class FakeWhisper:
    size, loaded = "fake", True

    def __init__(self, texto):
        self.texto = texto

    def load(self):
        pass

    def transcribe(self, audio, prompt=""):
        return self.texto


@pytest.fixture
def cliente(monkeypatch):
    import main

    monkeypatch.setattr(stt, "available", lambda: (True, ""))
    monkeypatch.setattr(stt, "get_transcriber", lambda: FakeWhisper("Jarvis, abre o Profit"))
    return TestClient(main.app)


def test_status(cliente):
    r = cliente.get("/v1/voice/status").json()
    assert r["available"] is True and r["wake_word"] == "jarvis"


def test_ws_ponta_a_ponta(cliente):
    with cliente.websocket_connect("/v1/voice/ws", headers={"origin": "http://localhost:5173"}) as ws:
        assert ws.receive_json()["type"] == "ready"
        audio = frase()
        for i in range(0, len(audio), 3200):
            ws.send_bytes(audio[i:i + 3200])
        assert ws.receive_json()["type"] == "wake"
        assert ws.receive_json() == {"type": "transcript", "text": "abre o Profit"}
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json() == {"type": "pong"}


def test_ws_recusa_origem_desconhecida(cliente):
    with pytest.raises(WebSocketDisconnect) as e:
        with cliente.websocket_connect("/v1/voice/ws", headers={"origin": "https://site-malicioso.com"}):
            pass
    assert e.value.code == 4403


def test_ws_aceita_o_hud_servido_pelo_backend(cliente):
    with cliente.websocket_connect("/v1/voice/ws", headers={"origin": "http://localhost:8000"}) as ws:
        assert ws.receive_json()["type"] == "ready"


def test_ws_sem_faster_whisper_avisa_e_fecha(monkeypatch):
    import main

    monkeypatch.setattr(stt, "available", lambda: (False, "Falta instalar o faster-whisper"))
    c = TestClient(main.app)
    with c.websocket_connect("/v1/voice/ws", headers={"origin": "http://localhost:5173"}) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and msg["code"] == "unavailable" and "faster-whisper" in msg["message"]
    assert c.get("/v1/voice/status").json()["available"] is False


def test_ws_voz_desligada(monkeypatch):
    import main

    monkeypatch.setattr(stt, "available", lambda: (True, ""))
    monkeypatch.setenv("JARVIS_VOICE_ENABLED", "0")
    c = TestClient(main.app)
    with c.websocket_connect("/v1/voice/ws") as ws:
        assert ws.receive_json()["code"] == "unavailable"
