"""Layout, interpretação de comandos, palavra de ativação e segmentação de voz (tudo puro, sem Windows)."""
import numpy as np
import pytest

from actions import intents, layout
from actions.layout import Monitor, Rect
from voice import wake
from voice.segmenter import SAMPLE_RATE, Segmenter


# ---------- layout ----------
M1 = Monitor(0, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1040), primary=True)
M2 = Monitor(1, Rect(1920, 0, 3840, 1080), Rect(1920, 0, 3840, 1080))


def test_um_monitor_divide_em_dois_tercos():
    p = layout.plan([M1], "auto", 2 / 3)
    assert p.mode == "split"
    assert p.app_rect == Rect(0, 0, 1280, 1040)
    assert p.jarvis_rect == Rect(1280, 0, 1920, 1040)  # o terço restante, sem vão


def test_dois_monitores_dedica_o_secundario_ao_jarvis():
    p = layout.plan([M1, M2], "auto")
    assert p.mode == "dedicated"
    assert (p.app_monitor, p.jarvis_monitor) == (0, 1)
    assert p.app_rect == M1.work and p.jarvis_rect == M2.work


def test_jarvis_monitor_escolhido_e_app_vai_para_o_outro():
    p = layout.plan([M1, M2], "auto", jarvis_monitor=0)
    assert (p.app_monitor, p.jarvis_monitor) == (1, 0)


def test_split_forcado_usa_o_monitor_onde_o_jarvis_esta():
    p = layout.plan([M1, M2], "split", 0.5, jarvis_rect=Rect(2000, 100, 2500, 600))
    assert p.mode == "split" and p.app_monitor == 1
    assert p.app_rect == Rect(1920, 0, 2880, 1080)


def test_dedicated_com_um_monitor_cai_para_split():
    assert layout.plan([M1], "dedicated").mode == "split"


def test_sem_monitores_levanta():
    with pytest.raises(ValueError):
        layout.plan([])


# ---------- comandos de abrir ----------
@pytest.mark.parametrize("fala,app,organiza", [
    ("abre o profit", "profit", True),
    ("Jarvis, abre o VS Code pra mim", "vs code", True),
    ("quero abrir o chrome", "chrome", True),
    ("por favor abra o bloco de notas", "bloco de notas", True),
    ("abre o profit em tela cheia", "profit", False),
    ("Abre o Profit, Jarvis.", "profit", True),
])
def test_parse_open(fala, app, organiza):
    r = intents.parse_open(fala)
    assert r and r.app == app and r.organize is organiza


@pytest.mark.parametrize("fala", [
    "abre o painel de rotinas", "abre um mapa do brasil", "como funciona o profit",
    "que horas são", "abre uma conversa sobre o mercado de câmbio hoje",
])
def test_parse_open_ignora_o_que_nao_e_programa(fala):
    r = intents.parse_open(fala)
    assert r is None or r.app_words > 3  # frase longa nunca vira "não encontrei"


@pytest.mark.parametrize("fala,esperado", [
    ("organiza a tela", "arrange"), ("divide a tela", "arrange"), ("arruma as janelas", "arrange"),
    ("me dá a tela toda", "jarvis_full"), ("tela cheia", "jarvis_full"), ("volta a tela cheia", "jarvis_full"),
    ("que dia é hoje", None), ("organiza minha agenda", None),
])
def test_parse_layout(fala, esperado):
    assert intents.parse_layout(fala) == esperado


@pytest.mark.parametrize("fala,kind,hint", [
    ("olha minha tela", "once", None),
    ("o que você está vendo?", "once", None),
    ("analisa o gráfico do profit", "once", "profit"),
    ("o que você acha desse gráfico", "once", None),
    ("vê o que tem na tela", "once", None),
    ("analisa comigo", "on", None),
    ("ativa o modo análise", "on", None),
    ("acompanha minha tela", "on", None),
    ("para de olhar a tela", "off", None),
    ("chega de olhar", "off", None),
    ("sai do modo copiloto", "off", None),
])
def test_parse_vision(fala, kind, hint):
    r = intents.parse_vision(fala)
    assert r and r.kind == kind and r.target_hint == hint


@pytest.mark.parametrize("fala", [
    "que horas são", "olha, me conta uma piada", "abre o profit para ver o gráfico", "qual a previsão do tempo",
])
def test_parse_vision_nao_dispara_sem_motivo(fala):
    assert intents.parse_vision(fala) is None


# ---------- palavra de ativação ----------
@pytest.mark.parametrize("texto,comando", [
    ("Jarvis, abre o Profit", "abre o Profit"),
    ("Ei, Jarvis!", ""),
    ("Garvis abre o vscode", "abre o vscode"),
    ("abre o profit, Jarvis", "abre o profit"),
    ("Jarvis", ""),
])
def test_find_wake(texto, comando):
    m = wake.find_wake(texto)
    assert m is not None and m.command == comando


@pytest.mark.parametrize("texto", [
    "eu vi o filme do Jarvis ontem à noite", "travis scott é bom", "abre o profit", "", "obrigado",
])
def test_find_wake_ignora_citacoes(texto):
    assert wake.find_wake(texto) is None


@pytest.mark.parametrize("texto,limpo", [
    ("Legendas pela comunidade Amara.org", ""), ("Tchau.", ""), ("", ""),
    ("abre o profit", "abre o profit"),
])
def test_clean_text(texto, limpo):
    assert wake.clean_text(texto) == limpo


# ---------- segmentador de fala ----------
def _tone(seconds, amp=0.3):
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * t) * amp * 32767).astype("<i2")


def _quiet(seconds, amp=0.002, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(SAMPLE_RATE * seconds)) * amp * 32767).astype("<i2")


def _feed(seg, audio, chunk=1600):
    out = []
    for i in range(0, len(audio), chunk):
        out += seg.feed(audio[i:i + chunk].tobytes())
    return out


def test_segmenta_uma_frase_com_ruido_de_fundo():
    seg = Segmenter()
    audio = np.concatenate([_quiet(1.0), _tone(1.0), _quiet(1.5, seed=1)])
    utts = _feed(seg, audio)
    assert len(utts) == 1
    assert 0.9 < utts[0].duration < 2.3  # inclui 300 ms antes e o silêncio final
    assert utts[0].audio.dtype == np.float32


def test_clique_curto_e_descartado():
    seg = Segmenter()
    assert _feed(seg, np.concatenate([_quiet(0.5), _tone(0.08), _quiet(1.5)])) == []


def test_duas_frases_separadas_por_silencio():
    seg = Segmenter()
    audio = np.concatenate([_quiet(0.5), _tone(0.8), _quiet(1.2), _tone(0.8), _quiet(1.2)])
    assert len(_feed(seg, audio)) == 2


def test_frase_muito_longa_e_cortada():
    seg = Segmenter(max_utterance_s=2.0)
    utts = _feed(seg, np.concatenate([_tone(5.0), _quiet(1.0)]))
    assert len(utts) >= 2


def test_pcm_com_byte_sobrando_nao_quebra():
    seg = Segmenter()
    assert seg.feed(b"\x00\x01\x02") == []
