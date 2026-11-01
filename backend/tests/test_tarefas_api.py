"""Fase 2 — rotas /v1/tarefas. Precisa do ambiente completo (FastAPI); a lógica está em test_tarefas_*.py."""
import copy
import json

import pytest

from routines.tools.registry import REGISTRY, Param, Tool

TAREFA = {
    "schema": 1, "id": "ola", "nome": "Olá",
    "contrato": {"escopo": {"ferramentas": ["t.ler"]}, "aprovado": True},
    "passos": [{"id": "ler", "ferramenta": "t.ler", "params": {}}],
}


@pytest.fixture(autouse=True)
def ferramenta(monkeypatch):
    async def ler():
        return {"type": "x", "title": "l", "data": {"itens": ["a"]}, "falado": "ok", "resumo_llm": ""}

    monkeypatch.setitem(REGISTRY, "t.ler", Tool("t.ler", "ler", "falsa", [], ler, "leitura"))


def t(**mudar):
    d = copy.deepcopy(TAREFA)
    d.update(mudar)
    return d


# ---- negados primeiro -----------------------------------------------------------------------------

@pytest.mark.parametrize("metodo,caminho", [
    ("get", "/v1/tarefas"), ("get", "/v1/tarefas/estado"), ("post", "/v1/tarefas"),
    ("post", "/v1/tarefas/ola/executar"), ("post", "/v1/tarefas/agendador/pausar"),
    ("post", "/v1/tarefas/importar"), ("delete", "/v1/tarefas/ola"),
])
def test_sem_token_401(anonimo, metodo, caminho):
    assert getattr(anonimo, metodo)(caminho).status_code == 401


def test_json_invalido_422(client):
    assert client.post("/v1/tarefas", json={"schema": 1, "id": "x"}).status_code == 422


def test_campo_desconhecido_422(client):
    assert client.post("/v1/tarefas", json=t(sorrateiro=1)).status_code == 422


def test_schema_futuro_422(client):
    assert client.post("/v1/tarefas", json=t(schema=99)).status_code == 422


def test_tarefa_inexistente_404(client):
    for m, c in [("get", "/v1/tarefas/nao"), ("post", "/v1/tarefas/nao/simular"), ("post", "/v1/tarefas/nao/executar"),
                 ("get", "/v1/tarefas/nao/execucoes"), ("delete", "/v1/tarefas/nao")]:
        assert getattr(client, m)(c).status_code == 404, c


def test_liberar_item_de_outra_tarefa_422(client):
    client.post("/v1/tarefas", json=t())
    assert client.delete("/v1/tarefas/ola/itens", params={"chave": "outra:abc"}).status_code == 422


def test_contrato_nao_aprovado_nao_executa(client, monkeypatch):
    chamadas = []

    async def ler():
        chamadas.append(1)
        return {"type": "x", "title": "l", "data": {}, "falado": "", "resumo_llm": ""}

    monkeypatch.setitem(REGISTRY, "t.ler", Tool("t.ler", "ler", "falsa", [], ler, "leitura"))
    d = t()
    d["contrato"]["aprovado"] = False
    client.post("/v1/tarefas", json=d)
    client.post("/v1/tarefas/ola/executar")
    assert chamadas == []


# ---- caminho feliz --------------------------------------------------------------------------------

def test_salvar_listar_obter_remover(client):
    r = client.post("/v1/tarefas", json=t())
    assert r.status_code == 200 and r.json()["id"] == "ola"
    assert [x["id"] for x in client.get("/v1/tarefas").json()["tarefas"]] == ["ola"]
    assert client.get("/v1/tarefas/ola").json()["tarefa"]["nome"] == "Olá"
    assert client.delete("/v1/tarefas/ola").status_code == 200
    assert client.get("/v1/tarefas").json()["tarefas"] == []


def test_ativar_e_desativar(client):
    client.post("/v1/tarefas", json=t())
    assert client.put("/v1/tarefas/ola/ativa", json={"ativa": False}).json() == {"ativa": False}
    assert client.get("/v1/tarefas/ola").json()["ativa"] is False


def test_simular_nao_registra_execucao(client):
    client.post("/v1/tarefas", json=t())
    r = client.post("/v1/tarefas/ola/simular")
    assert r.status_code == 200
    assert client.get("/v1/tarefas/ola/execucoes").json()["execucoes"] == []


def test_executar_cria_execucao_e_ela_termina(client):
    import time
    client.post("/v1/tarefas", json=t())
    r = client.post("/v1/tarefas/ola/executar")
    assert r.status_code == 200
    execucao = r.json()["execucao"]
    assert execucao is not None
    for _ in range(40):
        e = client.get(f"/v1/tarefas/execucoes/{execucao['id']}").json()
        if e["estado"] != "em_andamento":
            break
        time.sleep(0.05)
    assert e["estado"] == "ok"


def test_pausar_e_retomar_agendador(client):
    assert client.post("/v1/tarefas/agendador/pausar").json() == {"pausado": True}
    assert client.get("/v1/tarefas/estado").json()["pausado"] is True
    assert client.post("/v1/tarefas/agendador/retomar").json() == {"pausado": False}
    assert client.get("/v1/tarefas/estado").json()["pausado"] is False


def test_importar_pasta(client, tmp_path):
    from tarefas import pasta
    d = pasta.pasta()
    d.mkdir(parents=True, exist_ok=True)
    (d / "ola.json").write_text(json.dumps(t()), encoding="utf-8")
    (d / "quebrada.json").write_text("{nao é json", encoding="utf-8")
    r = client.post("/v1/tarefas/importar").json()
    assert len(r["resultados"]) == 2
    assert [x["id"] for x in client.get("/v1/tarefas").json()["tarefas"]] == ["ola"]
