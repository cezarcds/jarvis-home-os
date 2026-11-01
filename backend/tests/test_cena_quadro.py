"""Palavra-impacto e marcas desenhadas no roteiro do diretor."""
import re
from pathlib import Path

from scene_schema import MARK_ICONS, sanitize_scene

DIAGRAM = {"nodes": [{"id": "reator", "label": "Reator", "x": 20, "y": 50}, {"id": "vapor", "label": "Vapor", "x": 70, "y": 50}],
           "edges": [{"from": "reator", "to": "vapor"}]}
MEDIA = [{"id": f"m{i}", "kind": "image", "query": f"nuclear plant {i}", "tag": "foto 2019 de arquivo"} for i in range(1, 4)]


def beats(*raw):
    return sanitize_scene({"title": "Usina", "media": MEDIA, "diagram": DIAGRAM, "beats": list(raw)})["beats"]


def b(**kw):
    return {"say": "Fala qualquer.", "layout": "split", "media": "m1", **kw}


# ---------- palavra-impacto ----------
def test_impacto_valido_vira_maiusculo_e_mantem_tom():
    imp = beats(b(impact={"text": "verdade.", "at": 0.4, "tone": "alert"}))[0]["impact"]
    assert imp == {"text": "VERDADE", "at": 0.4, "tone": "alert"}


def test_impacto_aceita_texto_solto_e_usa_padroes():
    imp = beats(b(impact="calor"))[0]["impact"]
    assert imp["text"] == "CALOR" and imp["tone"] == "neutral" and 0 <= imp["at"] <= 0.85


def test_impacto_limita_a_duas_palavras_e_descarta_lixo():
    assert beats(b(impact={"text": "uma duas três quatro"}))[0]["impact"]["text"] == "UMA DUAS"
    for ruim in ({"text": "x"}, {"text": ""}, {"text": "a" * 30}, 42, None, [], {"tone": "alert"}):
        assert beats(b(impact=ruim))[0]["impact"] is None


def test_impacto_nunca_em_dois_beats_seguidos():
    out = beats(b(impact="UM"), b(impact="DOIS"), b(impact="TRES"))
    assert [x["impact"] is not None for x in out] == [True, False, True]


def test_tom_invalido_vira_neutral():
    assert beats(b(impact={"text": "OK", "tone": "gritante"}))[0]["impact"]["tone"] == "neutral"


# ---------- marcas ----------
def test_marcas_validas_passam_normalizadas():
    marks = beats(b(marks=[
        {"type": "circle", "target": "m1", "label": "o reator aqui", "at": 0.2},
        {"type": "arrow", "from": "m1", "to": "reator", "label": "vira vapor", "at": 0.5},
        {"type": "underline", "target": "vapor", "at": 0.8},
    ]))[0]["marks"]
    assert [m["type"] for m in marks] == ["circle", "arrow", "underline"]
    assert marks[0]["target"] == "m1" and marks[0]["label"] == "o reator aqui"
    assert marks[1]["target"] == "reator" and marks[1]["from"] == "m1"
    assert [m["at"] for m in marks] == sorted(m["at"] for m in marks)


def test_marca_com_alvo_inexistente_e_descartada():
    marks = beats(b(marks=[{"type": "circle", "target": "nao_existe"}, {"type": "arrow", "to": "xx"},
                           {"type": "circle", "target": "vapor"}]))[0]["marks"]
    assert [m["target"] for m in marks] == ["vapor"]


def test_seta_sem_origem_valida_continua_valendo():
    m = beats(b(marks=[{"type": "arrow", "from": "xx", "to": "m2"}]))[0]["marks"][0]
    assert m["from"] is None and m["target"] == "m2"


def test_colchete_precisa_de_dois_alvos_validos_sem_repeticao():
    ok = beats(b(marks=[{"type": "bracket", "targets": ["m1", "m2", "m2", "zz"], "label": "ideia formada"}]))[0]["marks"]
    assert ok[0]["targets"] == ["m1", "m2"] and ok[0]["label"] == "ideia formada"
    assert beats(b(marks=[{"type": "bracket", "targets": ["m1", "zz"]}]))[0]["marks"] == []
    assert beats(b(marks=[{"type": "bracket", "targets": "m1"}]))[0]["marks"] == []


def test_icone_so_com_nome_conhecido():
    marks = beats(b(marks=[{"type": "icon", "target": "m1", "icon": "bolt", "label": "energia"},
                           {"type": "icon", "target": "m2", "icon": "unicornio"}]))[0]["marks"]
    assert len(marks) == 1 and marks[0]["icon"] == "bolt"


def test_no_maximo_tres_marcas_e_tipos_estranhos_sao_ignorados():
    raw = [{"type": "circle", "target": "m1"}] * 6 + [{"type": "laser", "target": "m1"}, "x", None]
    assert len(beats(b(marks=raw))[0]["marks"]) == 3
    assert beats(b(marks=[{"type": "laser", "target": "m1"}, 5, None]))[0]["marks"] == []


def test_entradas_das_marcas_espacadas_e_dentro_da_fala():
    marks = beats(b(marks=[{"type": "circle", "target": "m1", "at": 0.9}, {"type": "circle", "target": "m2", "at": 0.9},
                           {"type": "underline", "target": "m3", "at": 0.91}]))[0]["marks"]
    ats = [m["at"] for m in marks]
    assert all(ats[i + 1] - ats[i] >= 0.09 for i in range(2)) and ats[-1] <= 0.92


def test_rotulo_longo_e_cortado_em_quatro_palavras():
    m = beats(b(marks=[{"type": "circle", "target": "m1", "label": "uma duas três quatro cinco seis."}]))[0]["marks"][0]
    assert m["label"] == "uma duas três quatro"


def test_tag_vertical_da_midia_e_maiuscula_e_curta():
    s = sanitize_scene({"title": "T", "media": MEDIA, "diagram": DIAGRAM, "beats": [b()]})
    assert s["media"][0]["tag"] == "FOTO 2019 DE ARQUIVO"
    assert sanitize_scene({"title": "T", "media": [{"id": "m1", "query": "abc def", "tag": "x" * 90}], "beats": [b()]})["media"][0]["tag"] == "X" * 24


def test_beats_sem_os_campos_novos_continuam_validos():
    out = beats({"say": "Só fala.", "layout": "media"})[0]
    assert out["impact"] is None and out["marks"] == []


def test_icones_do_backend_batem_com_a_biblioteca_do_frontend():
    js = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "stage" / "icons.js").read_text(encoding="utf-8")
    names = re.findall(r'^\s*"?([a-z][a-z-]*)"?\s*:\s*\[', js, flags=re.M)
    assert sorted(names) == sorted(MARK_ICONS)
