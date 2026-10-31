"""Chamadas de texto e mural de mídia no roteiro do diretor + telemetria do sistema."""
from fastapi.testclient import TestClient

import sysinfo
from main import app
from scene_schema import sanitize_scene

DIAGRAM = {"nodes": [{"id": "reator", "label": "Reator", "x": 20, "y": 50}, {"id": "vapor", "label": "Vapor", "x": 70, "y": 50}],
           "edges": [{"from": "reator", "to": "vapor"}]}
MEDIA = [{"id": f"m{i}", "kind": "image", "query": f"nuclear plant {i}"} for i in range(1, 7)]


def cena(beats, **extra):
    return sanitize_scene({"title": "Usina", "media": MEDIA, "diagram": DIAGRAM, "beats": beats, **extra})


def beat0(beats):
    return cena(beats)["beats"][0]


def test_chamadas_validas_passam_e_ficam_em_ordem():
    b = beat0([{"say": "O reator aquece a água e gera vapor.", "layout": "split", "media": "m1", "reveal": ["reator", "vapor"],
                "callouts": [{"text": "Gera vapor", "side": "right", "at": 0.7, "kind": "term", "target": "vapor"},
                             {"text": "Reator nuclear", "side": "left", "at": 0.2, "target": "reator"}]}])
    c = b["callouts"]
    assert [x["text"] for x in c] == ["Reator nuclear", "Gera vapor"]
    assert [x["side"] for x in c] == ["left", "right"] and c[0]["at"] < c[1]["at"]
    assert c[0]["target"] == "reator" and c[1]["kind"] == "term" and c[0]["kind"] == "fact"


def test_texto_longo_e_cortado_em_seis_palavras():
    b = beat0([{"say": "Fala.", "layout": "media", "callouts": [{"text": "uma duas três quatro cinco seis sete oito nove."}]}])
    assert b["callouts"][0]["text"] == "uma duas três quatro cinco seis"


def test_chamada_que_repete_a_fala_ou_a_outra_e_descartada():
    b = beat0([{"say": "Calor demais.", "layout": "media",
                "callouts": [{"text": "Calor demais!"}, {"text": "Alta pressão"}, {"text": "alta pressao"}]}])
    assert [c["text"] for c in b["callouts"]] == ["Alta pressão"]


def test_no_maximo_tres_e_lados_alternam_quando_nao_informados():
    b = beat0([{"say": "Fala.", "layout": "media", "callouts": [{"text": f"Item {i} aqui"} for i in range(1, 6)]}])
    c = b["callouts"]
    assert len(c) == 3 and [x["side"] for x in c] == ["left", "right", "left"]


def test_pontos_de_entrada_sao_espacados_e_cabem_na_fala():
    b = beat0([{"say": "Fala.", "layout": "media",
                "callouts": [{"text": "A aaa", "at": 0.5}, {"text": "B bbb", "at": 0.5}, {"text": "C ccc", "at": 0.51}]}])
    ats = [c["at"] for c in b["callouts"]]
    assert all(ats[i + 1] - ats[i] >= 0.13 for i in range(2)) and ats[-1] <= 0.92


def test_alvo_invalido_vira_none_e_valores_estranhos_nao_quebram():
    b = beat0([{"say": "Fala.", "layout": "media",
                "callouts": [{"text": "Qualquer coisa", "target": "nao_existe", "at": "abc", "side": "cima", "kind": "x"}, 42, None]}])
    c = b["callouts"][0]
    assert c["target"] is None and c["side"] in ("left", "right") and c["kind"] == "fact" and 0 <= c["at"] <= 0.92


def test_plano_b_usa_rotulos_do_que_entra_em_cena():
    b = beat0([{"say": "Entram o reator e o vapor.", "layout": "diagram", "reveal": ["reator", "vapor"]}])
    assert [c["text"] for c in b["callouts"]] == ["Reator", "Vapor"] and b["callouts"][0]["target"] == "reator"


def test_sem_nada_para_chamar_a_lista_fica_vazia():
    assert beat0([{"say": "Só conversa.", "layout": "title"}])["callouts"] == []


def test_mural_ate_quatro_midias_com_a_destacada_incluida():
    b = beat0([{"say": "Fala.", "layout": "media", "media": "m5", "show": ["m1", "m2", "m3", "m4", "m6", "xx"]}])
    assert b["media"] == "m5" and b["show"][0] == "m5" and len(b["show"]) == 4
    assert "xx" not in b["show"]


def test_ate_seis_midias_na_cena_e_show_ausente_vira_lista_vazia():
    s = cena([{"say": "Fala.", "layout": "media"}])
    assert len(s["media"]) == 6 and s["beats"][0]["show"] == []


def test_rota_de_cena_nao_perde_os_campos_novos():
    from scene_schema import fallback_scene

    b = fallback_scene("Uma resposta simples.")["beats"][0]
    assert b["callouts"] == [] and b["show"] == []


def test_telemetria_do_sistema(monkeypatch):
    class Fake:
        @staticmethod
        def cpu_percent(interval=None):
            return 17.6

        @staticmethod
        def virtual_memory():
            return type("M", (), {"percent": 54.2})()

    monkeypatch.setattr(sysinfo, "psutil", Fake)
    assert TestClient(app).get("/v1/system/stats").json() == {"cpu": 18, "mem": 54}
    monkeypatch.setattr(sysinfo, "psutil", None)
    assert TestClient(app).get("/v1/system/stats").status_code == 501
