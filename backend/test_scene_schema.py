"""Testes do saneamento de cenas. Rode com: python test_scene_schema.py"""
import json
from scene_schema import sanitize_scene, extract_json, fallback_scene, _resolve_overlaps


def test_messy_llm_output():
    raw = """```json
    {"title":"Como funciona uma usina nuclear","topic_kind":"process",
     "media":[{"id":"m1","kind":"image","query":"nuclear power plant cooling towers","caption":"Torres de resfriamento"},
              {"id":"m1","kind":"video","query":"xyz clip"}, {"kind":"image","query":"ab"}],
     "diagram":{"nodes":[
        {"id":"Reator","label":"Reator","detail":"A fissão aquece a água","kind":"source","icon":"atom","x":10,"y":50},
        {"id":"gerador_vapor","label":"Gerador de vapor","icon":"naoexiste","x":12,"y":52},
        {"id":"turbina","label":"Turbina","icon":"fan","x":60,"y":50},
        {"id":"gerador","label":"Gerador","x":85,"y":50},
        {"id":"x","label":""}],
      "edges":[{"from":"reator","to":"gerador_vapor","label":"calor"},
               {"from":"gerador_vapor","to":"turbina","label":"vapor"},
               {"from":"turbina","to":"gerador"},
               {"from":"turbina","to":"fantasma"},
               {"from":"turbina","to":"turbina"}]},
     "chart":{"series":[{"label":"a","value":1}]},
     "beats":[
       {"say":"Uma usina nuclear transforma calor em eletricidade.","layout":"media","media":"m1"},
       {"say":"No reator, a fissão aquece a água.","layout":"diagram","reveal":["reator","gerador_vapor"],"focus":["reator"]},
       {"say":"O vapor gira a turbina.","layout":"chart","reveal":["turbina"]},
       {"say":"Mapa?","layout":"eye"},
       {"say":"","layout":"diagram"}
     ]}
    ```"""
    scene = sanitize_scene(extract_json(raw))
    assert [m["id"] for m in scene["media"]] == ["m1", "m1_"], scene["media"]
    assert len(scene["diagram"]["nodes"]) == 4            # nó vazio descartado
    assert len(scene["diagram"]["edges"]) == 3            # fantasma e auto-laço descartados
    assert scene["diagram"]["nodes"][1]["icon"] is None   # ícone inválido
    assert chart_none(scene)                              # chart com 1 ponto cai
    layouts = [b["layout"] for b in scene["beats"]]
    assert layouts == ["media", "diagram", "diagram", "diagram"], layouts  # chart/eye sem dados rebaixados
    assert len(scene["beats"]) == 4                       # beat sem fala descartado
    # todos os nós aparecem em algum beat
    shown = {i for b in scene["beats"] for i in b["reveal"]}
    assert shown == {n["id"] for n in scene["diagram"]["nodes"]}, shown
    # nós sobrepostos foram afastados
    a, b = scene["diagram"]["nodes"][0], scene["diagram"]["nodes"][1]
    assert ((a["x"] - b["x"]) * 1.78) ** 2 + (a["y"] - b["y"]) ** 2 >= 15 ** 2
    for n in scene["diagram"]["nodes"]:
        assert 0 <= n["x"] <= 100 and 0 <= n["y"] <= 100


def chart_none(scene):
    return scene["chart"] is None


def test_auto_layout_without_coordinates():
    raw = {"beats": [{"say": "ok", "layout": "diagram"}],
           "diagram": {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"},
                                 {"id": "c", "label": "C"}, {"id": "d", "label": "D"}],
                       "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "c"}, {"from": "b", "to": "d"}]}}
    scene = sanitize_scene(raw)
    xs = {n["id"]: n["x"] for n in scene["diagram"]["nodes"]}
    assert xs["a"] < xs["b"] < xs["d"], xs
    assert xs["b"] == xs["c"]


def test_geo():
    raw = {"beats": [{"say": "Veja o mapa.", "layout": "eye"}],
           "geo": {"points": [{"label": "Santos", "lat": -23.96, "lon": -46.33, "layer": "Portos"},
                              {"label": "Roterdã", "lat": 51.9, "lon": 4.47, "layer": "Portos"},
                              {"label": "Lixo", "lat": 999, "lon": 0}],
                   "links": [{"from": "santos", "to": "roterda"}, {"from": "santos", "to": "zzz"}]}}
    scene = sanitize_scene(raw)
    assert len(scene["geo"]["points"]) == 3 or len(scene["geo"]["points"]) == 2
    assert scene["beats"][0]["layout"] == "eye"
    assert set(scene["beats"][0]["reveal"]) >= {"santos"}


def test_fallback_and_errors():
    fb = fallback_scene("Primeira frase. Segunda frase! Terceira?")
    assert fb["beats"] and fb["diagram"] is None
    for bad in ({}, {"beats": []}, {"beats": [{"say": ""}]}):
        try:
            sanitize_scene(bad)
        except ValueError:
            continue
        raise AssertionError("deveria falhar")
    try:
        extract_json("sem json aqui")
    except ValueError:
        pass
    else:
        raise AssertionError


def test_overlap_resolver_converges():
    nodes = [{"x": 50.0, "y": 50.0} for _ in range(6)]
    _resolve_overlaps(nodes)
    pts = [(n["x"], n["y"]) for n in nodes]
    assert len(set(pts)) == 6


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
