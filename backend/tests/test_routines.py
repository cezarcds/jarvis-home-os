import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("GROQ_API_KEY", "x")

from fastapi.testclient import TestClient  # noqa: E402

import llm  # noqa: E402
from main import app  # noqa: E402
from routines import creator, store  # noqa: E402
from routines.tools import REGISTRY  # noqa: E402

client = TestClient(app)


def _fake_tool(tipo, titulo, falado):
    async def fn(**kw):
        return {"type": tipo, "title": titulo, "data": {"kw": kw, "dias": [], "itens": []},
                "falado": falado, "resumo_llm": falado}
    return fn


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "FILE", tmp_path / "routines.json")
    creator.PENDING.clear()
    for name, tipo, falado in [("agenda.hoje", "agenda", "Você tem 2 compromissos hoje."),
                               ("agenda.amanha", "agenda", "Amanhã sua agenda está livre."),
                               ("gmail.para_responder", "emails", "Há 3 emails aguardando resposta."),
                               ("clima.agora", "clima", "Agora faz 24 graus.")]:
        monkeypatch.setattr(REGISTRY[name], "check", None)
        monkeypatch.setattr(REGISTRY[name], "fn", _fake_tool(tipo, name, falado))
    yield


def usar_llm(monkeypatch, handler):
    async def fake(messages, system=None, **kw):
        return handler(messages, system or ""), "fake"
    monkeypatch.setattr(llm, "complete", fake)


def falar(texto, sid="s1"):
    r = client.post("/v1/assistant", json={"messages": [{"role": "user", "content": texto}], "session_id": sid})
    assert r.status_code == 200, r.text
    return r.json()


def test_gatilho_direto_com_fallback_template(monkeypatch):
    async def boom(*a, **k):
        raise llm.LLMError("sem rede")
    monkeypatch.setattr(llm, "complete", boom)
    r = falar("Bom dia, Jarvis!")
    assert r["kind"] == "rotina"
    assert [b["id"] for b in r["scene"]["blocos"]] == ["agenda", "emails", "clima"]
    assert "2 compromissos" in r["text"] and "24 graus" in r["text"]


def test_resumo_por_llm(monkeypatch):
    usar_llm(monkeypatch, lambda m, s: "Bom dia. Você tem dois compromissos.")
    r = falar("bom dia")
    assert r["text"] == "Bom dia. Você tem dois compromissos."


def test_roteamento_por_significado(monkeypatch):
    def h(m, s):
        if s.startswith("Você classifica"):
            return json.dumps({"tipo": "rotina", "id": "bom-dia", "params": {}, "confianca": 0.92})
        return "Resumo falado."
    usar_llm(monkeypatch, h)
    r = falar("me conta como vai ser meu dia")
    assert r["kind"] == "rotina" and r["scene"]["rotina"]["id"] == "bom-dia"


def test_ferramenta_avulsa(monkeypatch):
    def h(m, s):
        if s.startswith("Você classifica"):
            return '```json\n{"tipo":"ferramenta","id":"agenda.amanha","params":{},"confianca":0.9}\n```'
        return "Amanhã você está livre."
    usar_llm(monkeypatch, h)
    r = falar("que reuniões eu tenho depois de hoje?")
    assert r["kind"] == "rotina" and r["scene"]["blocos"][0]["type"] == "agenda"


def test_conversa_comum(monkeypatch):
    def h(m, s):
        if s.startswith("Você classifica"):
            return json.dumps({"tipo": "conversa", "id": None, "params": {}, "confianca": 0.9})
        assert "NÃO tem acesso" in s
        return "Paris."
    usar_llm(monkeypatch, h)
    r = falar("qual a capital da França?")
    assert r["kind"] == "chat" and r["text"] == "Paris." and r["scene"] is None


def rascunho_json(**over):
    base = {"acao": "criar", "alvo": None, "faltando": ["TikTok"], "observacao": "",
            "rotina": {"nome": "Fim de expediente", "descricao": "d",
                       "gatilhos": ["encerrar o expediente", "acabou o dia de trabalho"],
                       "tipo": "leitura",
                       "passos": [{"id": "agenda", "ferramenta": "agenda.amanha", "params": {}},
                                  {"id": "emails", "ferramenta": "gmail.para_responder", "params": {"max": "4"}}],
                       "tela": {"titulo": "Fim de expediente", "blocos": ["agenda", "emails"]},
                       "fala": {"modo": "template", "instrucao": None}}}
    base.update(over)
    return json.dumps(base)


def test_criar_rotina_por_voz_e_usar(monkeypatch):
    usar_llm(monkeypatch, lambda m, s: rascunho_json() if s.startswith("Você converte") else "x")
    r = falar("cria uma rotina de fim de expediente com agenda de amanhã e emails, e o tiktok")
    assert r["kind"] == "rascunho" and "TikTok" in r["text"] and "Confirma?" in r["text"]
    assert r["scene"]["blocos"][0]["type"] == "rascunho"
    assert store.get("fim-de-expediente") is None  # ainda não gravou
    r = falar("confirma")
    assert r["kind"] == "rotina_salva" and store.get("fim-de-expediente")
    assert store.get("fim-de-expediente").passos[1].params == {"max": "4"}
    r = falar("encerrar o expediente")  # gatilho recém-criado funciona direto
    assert r["kind"] == "rotina" and r["scene"]["rotina"]["id"] == "fim-de-expediente"
    assert "Amanhã sua agenda está livre." in r["text"]


def test_cancelar_rascunho(monkeypatch):
    usar_llm(monkeypatch, lambda m, s: rascunho_json())
    falar("crie uma rotina nova")
    assert falar("cancela")["kind"] == "cancelado"
    assert creator.get_pending("s1") is None
    falar("confirma")  # sem rascunho pendente, não grava nada
    assert store.get("fim-de-expediente") is None


def test_refinar_rascunho(monkeypatch):
    vistos = {}

    def h(m, s):
        vistos["prompt"] = m[0]["content"]
        return rascunho_json()
    usar_llm(monkeypatch, h)
    falar("cria uma rotina de fim de expediente")
    falar("troca o nome para Encerramento")
    assert "RASCUNHO ATUAL" in vistos["prompt"]


def test_rascunho_invalido_vira_erro(monkeypatch):
    ruim = rascunho_json()
    d = json.loads(ruim)
    d["rotina"]["passos"][0]["ferramenta"] = "tiktok.postar"
    usar_llm(monkeypatch, lambda m, s: json.dumps(d))
    r = falar("cria uma rotina que posta no tiktok")
    assert r["kind"] == "rascunho" and r["scene"]["blocos"][0]["type"] == "erro"
    assert not creator.get_pending("s1")


def test_rotina_de_acao_rejeitada(monkeypatch):
    d = json.loads(rascunho_json())
    d["rotina"]["tipo"] = "acao"
    usar_llm(monkeypatch, lambda m, s: json.dumps(d))
    r = falar("cria uma rotina que limpa minha caixa de email")
    assert r["scene"]["blocos"][0]["type"] == "erro"


def test_apagar_por_voz(monkeypatch):
    usar_llm(monkeypatch, lambda m, s: json.dumps({"acao": "apagar", "alvo": "fim-do-dia", "rotina": None, "faltando": []}))
    r = falar("apaga a rotina fim do dia")
    assert "apagar a rotina Fim do dia" in r["text"]
    falar("sim")
    assert store.get("fim-do-dia") is None


def test_listar_rotinas():
    r = falar("quais são as minhas rotinas")
    assert r["kind"] == "lista" and r["scene"]["blocos"][0]["type"] == "rotinas"


def test_crud_http():
    assert len(client.get("/v1/routines").json()) == 2
    nova = {"nome": "Teste", "gatilhos": ["testando"], "passos": [{"id": "c", "ferramenta": "clima.agora"}],
            "fala": {"modo": "template"}}
    r = client.post("/v1/routines", json=nova)
    assert r.status_code == 200 and r.json()["id"] == "teste"
    nova["nome"] = "Teste 2"
    assert client.put("/v1/routines/teste", json=nova).json()["nome"] == "Teste 2"
    run = client.post("/v1/routines/teste/run").json()
    assert run["scene"]["blocos"][0]["type"] == "clima" and "24 graus" in run["text"]
    assert client.delete("/v1/routines/teste").status_code == 200
    assert client.delete("/v1/routines/teste").status_code == 404
    ruim = {**nova, "passos": [{"id": "c", "ferramenta": "nao.existe"}]}
    assert client.post("/v1/routines", json=ruim).status_code == 422
    assert client.post("/v1/routines", json={**nova, "tipo": "acao"}).status_code == 422
    dup = {**nova, "passos": [{"id": "a", "ferramenta": "clima.agora"}, {"id": "a", "ferramenta": "clima.agora"}]}
    assert client.post("/v1/routines", json=dup).status_code == 422


def test_ferramenta_indisponivel_vira_bloco_de_erro(monkeypatch):
    monkeypatch.setattr(REGISTRY["agenda.hoje"], "check", lambda: (False, "Google não autorizado."))
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("x")))
    r = falar("bom dia")
    tipos = {b["id"]: b["type"] for b in r["scene"]["blocos"]}
    assert tipos["agenda"] == "erro" and tipos["clima"] == "clima"
    assert "Não consegui consultar: agenda de hoje" in r["text"]


def test_tools_e_health():
    assert any(t["nome"] == "agenda.hoje" for t in client.get("/v1/tools").json())
    assert client.get("/health").json()["status"] == "ok"
