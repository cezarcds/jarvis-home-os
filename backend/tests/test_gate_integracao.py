"""Fase 1 — gate ligado ao app real: endpoints, comando de voz 'para tudo', motor de rotinas e handler.
Precisa do ambiente completo (FastAPI etc.); a lógica pura do gate está em test_gate.py."""
import asyncio

import pytest

from actions import gate, handler
from connections import db
from routines import engine
from routines.models import Fala, Routine, Step, Tela
from routines.tools import REGISTRY
from routines.tools.registry import Param, Tool


@pytest.fixture
def rascunho(monkeypatch):
    """Ferramenta falsa de nível 2 (como um futuro gmail.rascunhar)."""
    chamadas = []

    async def fn(**p):
        chamadas.append(p)
        return {"type": "acao", "title": "Rascunho", "data": {}, "falado": "Rascunho criado.", "resumo_llm": ""}

    monkeypatch.setitem(REGISTRY, "x.rascunho", Tool("x.rascunho", "criar rascunho", "falsa",
                        [Param("para", "str", "ana@example.com")], fn, "externo_reversivel"))
    return chamadas


def criar_pendente(sid="s1"):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        asyncio.run(gate.executar("x.rascunho", {"para": "ana@example.com"}, gate.Contexto(sid=sid)))
    return exc.value.pendente


# ---- endpoints ----------------------------------------------------------------------------------

def test_listar_pendentes_nao_expoe_parametros(client, rascunho):
    pend = criar_pendente()
    r = client.get("/v1/gate/pendentes")
    assert r.status_code == 200
    item = r.json()["pendentes"][0]
    assert item["id"] == pend["id"] and "params" not in item and "ana@example.com" in item["texto"]


def test_confirmar_executa_uma_vez(client, rascunho):
    pend = criar_pendente()
    r = client.post(f"/v1/gate/{pend['id']}/confirmar")
    assert r.status_code == 200 and "Rascunho criado" in r.json()["text"]
    assert rascunho == [{"para": "ana@example.com"}]
    assert client.post(f"/v1/gate/{pend['id']}/confirmar").status_code == 409   # uso único
    assert len(rascunho) == 1


def test_confirmar_id_errado_409_e_nao_executa(client, rascunho):
    criar_pendente()
    assert client.post("/v1/gate/00000000/confirmar").status_code == 409
    assert rascunho == []


def test_confirmar_expirada_409(client, rascunho, monkeypatch):
    pend = criar_pendente()
    t0 = gate.agora()
    monkeypatch.setattr(gate, "_clock", lambda: t0 + gate.PENDENTE_TTL_S + 1)
    assert client.post(f"/v1/gate/{pend['id']}/confirmar").status_code == 409
    assert rascunho == []


def test_negar_nao_executa(client, rascunho):
    pend = criar_pendente()
    assert client.post(f"/v1/gate/{pend['id']}/negar").status_code == 200
    assert client.post(f"/v1/gate/{pend['id']}/confirmar").status_code == 409
    assert rascunho == []


def test_botao_de_parada_descarta_pendentes(client, rascunho):
    pend = criar_pendente()
    r = client.post("/v1/gate/parar")
    assert r.status_code == 200 and r.json()["pendentes_descartadas"] == 1
    assert client.post(f"/v1/gate/{pend['id']}/confirmar").status_code == 409
    assert rascunho == []


# ---- voz ----------------------------------------------------------------------------------------

def test_para_tudo_por_voz_interrompe_sem_chamar_llm(client, rascunho, monkeypatch):
    import llm

    async def nao_deve_chamar(*a, **k):
        raise AssertionError("o comando de parada não pode depender de LLM")

    monkeypatch.setattr(llm, "complete", nao_deve_chamar)
    pend = criar_pendente("s1")
    r = client.post("/v1/assistant", json={"messages": [{"role": "user", "content": "Jarvis, para tudo"}],
                                           "session_id": "s1"})
    assert r.status_code == 200 and r.json()["kind"] == "parada"
    assert client.post(f"/v1/gate/{pend['id']}/confirmar").status_code == 409


# ---- handler (voz, texto e LLM) -----------------------------------------------------------------------

def test_llm_pedindo_acao_de_nivel_2_cai_em_confirmacao(rascunho):
    r = asyncio.run(handler.run_tool("x.rascunho", {"para": "ana@example.com"}, "s1"))
    assert r["kind"] == "confirmacao" and r["pendente"]["forte"] is False
    assert "ana@example.com" in r["pendente"]["texto"] and rascunho == []


# ---- motor de rotinas ----------------------------------------------------------------------------------

def _rotina(ferramenta, params=None):
    return Routine(id="t", nome="Teste", passos=[Step(id="p", ferramenta=ferramenta, params=params or {})],
                   tela=Tela(blocos=["p"]), fala=Fala(modo="template"))


def test_rotina_nao_executa_acao_e_registra_a_negativa():
    out = asyncio.run(engine.run_routine(_rotina("app.abrir", {"app": "profit"}), "s1"))
    assert out["blocos"][0]["type"] == "erro" and "não habilitadas" in out["blocos"][0]["data"]["mensagem"]
    neg = [r for r in db.recent_actions(10) if r["tool"] == "app.abrir"]
    assert neg and neg[0]["resultado"] == "negado" and neg[0]["origem"] == "rotina"


def test_rotina_de_leitura_passa_pelo_gate_e_contamina(monkeypatch):
    async def fn(**p):
        return {"type": "agenda", "title": "Agenda", "data": {}, "falado": "Livre.", "resumo_llm": "Livre."}

    monkeypatch.setattr(REGISTRY["agenda.hoje"], "check", None)
    monkeypatch.setattr(REGISTRY["agenda.hoje"], "fn", fn)
    out = asyncio.run(engine.run_routine(_rotina("agenda.hoje"), "s9"))
    assert out["blocos"][0]["type"] == "agenda"
    assert [r["resultado"] for r in db.recent_actions(10) if r["tool"] == "agenda.hoje"][0] == "ok"
    assert gate.sessao_contaminada("s9") and not gate.sessao_contaminada("outra")


def test_rotina_cancelada_pela_parada_nao_roda_o_passo(monkeypatch):
    chamou = []

    async def fn(**p):
        chamou.append(1)
        return {"type": "agenda", "title": "A", "data": {}, "falado": "x", "resumo_llm": "x"}

    monkeypatch.setattr(REGISTRY["agenda.hoje"], "check", None)
    monkeypatch.setattr(REGISTRY["agenda.hoje"], "fn", fn)
    original = gate.Contexto

    def contexto_ja_parado(**kw):
        c = original(**kw)
        gate.parar("teste")      # a parada acontece depois que o contexto nasceu
        return c

    monkeypatch.setattr(gate, "Contexto", contexto_ja_parado)
    out = asyncio.run(engine.run_routine(_rotina("agenda.hoje"), "s1"))
    assert chamou == [] and out["blocos"][0]["data"]["mensagem"] == "Interrompido"
