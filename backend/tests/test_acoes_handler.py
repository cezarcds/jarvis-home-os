"""Ações e visão ponta a ponta (rota /v1/assistant) com Windows e Gemini simulados."""
import os
import sys
import types
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

import llm  # noqa: E402
from actions import apps, handler, vision  # noqa: E402
from actions.layout import Monitor, Rect  # noqa: E402
from actions.winapi import WindowInfo  # noqa: E402
from main import app  # noqa: E402
from routines import creator, store  # noqa: E402

client = TestClient(app)

M1 = Monitor(0, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1040), primary=True)
HUD = WindowInfo(1, "JARVIS // Home OS", "chrome.exe", Rect(600, 100, 1300, 800))


class FakeWin:
    AVAILABLE = True

    def __init__(self, windows, monitors=None):
        self.windows = list(windows)
        self._monitors = monitors or [M1]
        self.placed, self.fronted, self.fg = {}, [], None

    def enable_dpi_awareness(self):
        pass

    def list_windows(self, include_minimized=True):
        return [w for w in self.windows if include_minimized or not w.minimized]

    def monitors(self):
        return self._monitors

    def foreground_hwnd(self):
        return self.fg

    def place(self, hwnd, rect):
        self.placed[hwnd] = rect

    def bring_to_front(self, hwnd):
        self.fronted.append(hwnd)


@pytest.fixture
def mundo(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "FILE", tmp_path / "routines.json")
    creator.PENDING.clear()
    handler.reset_state()
    w = types.SimpleNamespace(win=FakeWin([HUD]), launched=[], grabs=0, llm_calls=[])
    monkeypatch.setattr(handler, "win", w.win)
    monkeypatch.setattr(apps, "time", types.SimpleNamespace(sleep=lambda s: None, time=time.time))

    def fake_launch(entry):
        w.launched.append(entry.id)
        w.win.windows.append(WindowInfo(2, "projeto - Visual Studio Code", "code.exe", Rect(0, 0, 800, 600)))

    monkeypatch.setattr(apps, "launch", fake_launch)

    def fake_grab(region):
        w.grabs += 1
        return vision.Capture(b"JPEG", "", 100, 100)

    monkeypatch.setattr(vision, "grab_region", fake_grab)

    async def fake_llm(messages, system=None, images=None, **kw):
        w.llm_calls.append({"messages": messages, "system": system, "images": images})
        return "Leitura da tela: tendência de alta.", "gemini"

    monkeypatch.setattr(llm, "complete", fake_llm)
    return w


def falar(texto, sid="s1", extra=None):
    msgs = (extra or []) + [{"role": "user", "content": texto}]
    r = client.post("/v1/assistant", json={"messages": msgs, "session_id": sid})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- abrir programas e layout ----------
def test_abre_vscode_e_divide_a_tela(mundo):
    r = falar("Jarvis, abre o VS Code")
    assert r["kind"] == "acao" and "VS Code" in r["text"] and "organizei" in r["text"]
    assert mundo.launched == ["vscode"]
    assert mundo.win.placed[2] == Rect(0, 0, 1280, 1040)      # programa em 2/3
    assert mundo.win.placed[1] == Rect(1280, 0, 1920, 1040)   # Jarvis no 1/3 restante
    assert mundo.win.fronted[-1] == 2


def test_programa_ja_aberto_nao_abre_de_novo(mundo):
    mundo.win.windows.append(WindowInfo(2, "x - Visual Studio Code", "code.exe", Rect(0, 0, 10, 10)))
    r = falar("abre o vscode")
    assert mundo.launched == [] and "já estava aberto" in r["text"]
    assert mundo.win.placed[2] == Rect(0, 0, 1280, 1040)


def test_tela_cheia_nao_organiza(mundo):
    r = falar("abre o vs code em tela cheia")
    assert mundo.launched == ["vscode"] and mundo.win.placed == {}
    assert r["text"] == "Abri o VS Code."


def test_sem_janela_do_jarvis_avisa(mundo):
    mundo.win.windows.remove(HUD)
    r = falar("abre o vs code")
    assert 2 in mundo.win.placed and 1 not in mundo.win.placed
    assert "minha janela" in r["text"]


def test_programa_desconhecido(mundo):
    r = falar("abre o xyzabc")
    assert r["kind"] == "acao" and "Não encontrei" in r["text"] and mundo.launched == []


def test_frase_longa_sobre_abrir_segue_para_o_chat(mundo):
    r = falar("abre uma conversa sobre o mercado de câmbio hoje")
    assert r["kind"] == "chat"


def test_organiza_a_tela_usa_a_janela_em_foco(mundo):
    mundo.win.windows.append(WindowInfo(3, "Profit Pro - WINFUT", "profitchart.exe", Rect(0, 0, 500, 500)))
    mundo.win.fg = 3
    r = falar("organiza a tela")
    assert r["kind"] == "acao" and mundo.win.placed[3] == Rect(0, 0, 1280, 1040)


def test_jarvis_tela_cheia(mundo):
    r = falar("tela cheia")
    assert r["kind"] == "acao" and mundo.win.placed[1] == M1.work


def test_vscode_com_dois_monitores_vai_para_o_principal(mundo):
    m2 = Monitor(1, Rect(1920, 0, 3840, 1080), Rect(1920, 0, 3840, 1080))
    mundo.win._monitors = [M1, m2]
    r = falar("abre o vs code")
    assert mundo.win.placed[2] == M1.work and mundo.win.placed[1] == m2.work
    assert "monitor principal" in r["text"]


def test_acoes_desligadas(mundo, monkeypatch):
    monkeypatch.setenv("JARVIS_ACTIONS_ENABLED", "0")
    r = falar("abre o vs code")
    assert mundo.launched == [] and r["kind"] == "chat"


def test_rotina_nao_aceita_passo_de_acao():
    nova = {"nome": "Teste", "gatilhos": ["testando"], "passos": [{"id": "a", "ferramenta": "app.abrir",
            "params": {"app": "profit"}}], "fala": {"modo": "template"}}
    r = client.post("/v1/routines", json=nova)
    assert r.status_code == 422 and "ação" in r.text


# ---------- visão ----------
def _com_profit(mundo):
    mundo.win.windows.append(WindowInfo(3, "Profit Pro - WINFUT", "profitchart.exe", Rect(0, 0, 1280, 1040)))
    mundo.win.fg = 3


def test_olha_a_tela_manda_a_imagem_ao_gemini(mundo):
    _com_profit(mundo)
    r = falar("olha minha tela")
    assert r["kind"] == "visao" and "tendência" in r["text"]
    call = mundo.llm_calls[-1]
    assert call["images"] == [b"JPEG"] and "Profit Pro" in call["system"]
    assert "Descreva" in call["messages"][-1]["content"]      # "olha a tela" vira uma pergunta útil
    assert r["vision"]["active"] is True and r["vision"]["mode"] == "off"


def test_pergunta_seguinte_reaproveita_a_imagem(mundo):
    _com_profit(mundo)
    falar("olha minha tela")
    r = falar("e o volume, como está?")
    assert r["kind"] == "visao"
    assert mundo.grabs == 1 and mundo.llm_calls[-1]["images"] == [b"JPEG"]
    assert mundo.llm_calls[-1]["messages"][-1]["content"] == "e o volume, como está?"


def test_modo_analise_captura_de_novo_a_cada_pergunta(mundo):
    _com_profit(mundo)
    r = falar("analisa comigo")
    assert "Modo análise ligado" in r["text"] and r["vision"]["mode"] == "on"
    assert mundo.llm_calls == []                              # ligar o modo não gasta chamada ao modelo
    falar("e agora?")
    falar("e agora?")
    assert mundo.grabs == 3


def test_parar_de_olhar_desliga_e_esquece_a_imagem(mundo):
    _com_profit(mundo)
    falar("analisa comigo")
    r = falar("para de olhar a tela")
    assert r["vision"]["mode"] == "off" and r["vision"]["active"] is False
    assert handler.vision_active("s1") is False


def test_alvo_pelo_nome_do_programa(mundo):
    _com_profit(mundo)
    mundo.win.fg = None
    r = falar("analisa o gráfico do profit")
    assert r["kind"] == "visao" and "Profit" in mundo.llm_calls[-1]["system"]


def test_programa_pedido_sem_janela_aberta(mundo):
    r = falar("olha o profit")
    assert r["kind"] == "visao" and "Não encontrei uma janela aberta do Profit" in r["text"]
    assert mundo.llm_calls == []


def test_janela_sensivel_bloqueia_a_captura(mundo):
    _com_profit(mundo)
    mundo.win.windows.insert(0, WindowInfo(4, "Nubank - Google Chrome", "chrome.exe", Rect(100, 100, 600, 600)))
    r = falar("olha minha tela")
    assert "sensível" in r["text"] and mundo.grabs == 0 and mundo.llm_calls == []


def test_janela_minimizada(mundo):
    mundo.win.windows.append(WindowInfo(3, "Profit Pro", "profitchart.exe", Rect(0, 0, 10, 10), minimized=True))
    mundo.win.fg = 3
    r = falar("olha o profit")
    assert "Não encontrei" in r["text"] or "minimizada" in r["text"]
    assert mundo.grabs == 0


def test_visao_desligada(mundo, monkeypatch):
    monkeypatch.setenv("JARVIS_VISION_ENABLED", "0")
    r = falar("olha minha tela")
    assert "desligada" in r["text"] and mundo.grabs == 0


def test_falha_do_gemini_nao_derruba(mundo, monkeypatch):
    _com_profit(mundo)

    async def boom(*a, **k):
        raise llm.LLMError("sem rede")

    monkeypatch.setattr(llm, "complete", boom)
    r = falar("olha minha tela")
    assert r["kind"] == "visao" and "não consegui analisar" in r["text"]


# ---------- Gemini com imagem ----------
def test_gemini_recebe_a_imagem_na_ultima_fala_do_usuario(monkeypatch):
    import asyncio

    sent = {}

    class FakeResp:
        is_error = False

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            sent["url"], sent["json"] = url, json
            return FakeResp()

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    msgs = [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"},
            {"role": "user", "content": "e esse gráfico?"}]
    text, provider = asyncio.run(llm.complete(msgs, system="s", images=[b"abc"]))
    assert (text, provider) == ("ok", "gemini")          # Groq não enxerga imagem: só o Gemini é usado
    parts = sent["json"]["contents"][-1]["parts"]
    assert parts[-1]["inline_data"]["mime_type"] == "image/jpeg" and parts[-1]["inline_data"]["data"] == "YWJj"
    assert len(sent["json"]["contents"][0]["parts"]) == 1  # a imagem não vai nas falas antigas


def test_imagem_sem_chave_do_gemini(monkeypatch):
    import asyncio

    monkeypatch.setenv("GROQ_API_KEY", "g")
    with pytest.raises(llm.LLMError, match="GEMINI_API_KEY"):
        asyncio.run(llm.complete([{"role": "user", "content": "x"}], images=[b"x"]))


# ---------- catálogo ----------
@pytest.mark.parametrize("fala,id_", [
    ("profit", "profit"), ("profit pro", "profit"), ("vs code", "vscode"), ("visual studio code", "vscode"),
    ("vscode", "vscode"), ("google chrome", "chrome"), ("bloco de notas", "notepad"), ("calculadora", "calculadora"),
])
def test_resolve_apelidos(fala, id_):
    assert apps.resolve(fala).id == id_


def test_resolve_desconhecido():
    assert apps.resolve("xyzabc") is None and apps.resolve("") is None


def test_apps_json_do_usuario_adiciona_e_substitui(tmp_path, monkeypatch):
    import json

    from connections.config import data_dir

    (data_dir() / "apps.json").write_text(json.dumps([
        {"id": "profit", "nomes": ["profit"], "comandos": [r"C:\Nelogica\profitchart.exe"], "titulo_regex": "Profit"},
        {"id": "obs", "nomes": ["obs", "gravador"], "comandos": ["obs64.exe"], "rotulo": "OBS"},
        {"id": "quebrado"},
    ]), encoding="utf-8")
    cat = {e.id: e for e in apps.load_catalog()}
    assert cat["profit"].comandos == [r"C:\Nelogica\profitchart.exe"]   # o seu sobrescreve o padrão
    assert cat["obs"].falado == "OBS" and apps.resolve("gravador", list(cat.values())).id == "obs"
    assert "quebrado" not in cat and "vscode" in cat                    # entrada inválida é ignorada, padrões ficam


# ---------- diagnóstico ----------
def test_rotas_de_diagnostico(mundo):
    mundo.win.windows.append(WindowInfo(3, "Profit Pro - WINFUT", "profitchart.exe", Rect(0, 0, 10, 10)))
    ids = {a["id"] for a in client.get("/v1/actions/apps").json()}
    assert {"profit", "vscode", "chrome"} <= ids
    wins = {w["titulo"]: w for w in client.get("/v1/actions/windows").json()}
    assert wins["Profit Pro - WINFUT"]["processo"] == "profitchart.exe" and wins["Profit Pro - WINFUT"]["jarvis"] is False
    assert wins["JARVIS // Home OS"]["jarvis"] is True


def test_windows_fora_do_windows(monkeypatch):
    monkeypatch.setattr(handler, "win", types.SimpleNamespace(AVAILABLE=False))
    assert client.get("/v1/actions/windows").status_code == 501
