import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json, scene_schema as S

def beat(say, layout, **kw):
    return {"say": say, "layout": layout, "callouts": [{"text":"Chamada curta","side":"left"}],
            "impact": {"text":"CALOR","at":0.4}, "marks": [], **kw}

media = [{"id":"m1","kind":"image","query":"nuclear power plant"}]
board = {"title":"Como funciona","items":[
    {"icon":"atom","label":"Fissão do átomo","detail":"o núcleo se divide"},
    {"icon":"flame","label":"Calor"},
    {"icon":"xxx","label":"Vapor movendo turbina elétrica"},   # ícone inválido + rótulo longo
]}

def run(name, raw):
    sc = S.sanitize_scene(raw)
    print(f"\n== {name}")
    print("   layouts:", [b["layout"] for b in sc["beats"]], "| board:", bool(sc["board"]))
    for i,b in enumerate(sc["beats"]):
        if b["layout"]=="board":
            print(f"   beat {i}: callouts={len(b['callouts'])} impact={b['impact']} marks={len(b['marks'])}")
    return sc

# 1) quadro usado normalmente
sc = run("quadro usado", {"title":"Usina","media":media,"board":board,
    "beats":[beat("Abertura.","media",media="m1"), beat("Primeiro, fissão. Depois calor e vapor.","board"), beat("Fim.","media")]})
assert sc["beats"][1]["layout"]=="board" and sc["beats"][1]["callouts"]==[] and sc["beats"][1]["impact"] is None
it = sc["board"]["items"]
assert it[2]["icon"] is None and len(it[2]["label"])<=22, it
assert it[0]["icon"]=="atom"

# 2) quadro enviado mas nenhum beat o usa -> um beat é promovido
sc = run("quadro esquecido", {"title":"x","media":media,"board":board,
    "beats":[beat("a.","media"), beat("b.","media"), beat("c.","media")]})
assert sum(b["layout"]=="board" for b in sc["beats"])==1
assert [b for b in sc["beats"] if b["layout"]=="board"][0]["callouts"]==[]

# 3) dois beats pedindo board -> só o primeiro
sc = run("dois board", {"title":"x","media":media,"board":board,
    "beats":[beat("a.","board"), beat("b.","board"), beat("c.","media")]})
assert [b["layout"] for b in sc["beats"]].count("board")==1 and sc["beats"][0]["layout"]=="board"

# 4) layout board SEM bloco board -> rebaixado, nunca chega ao palco
sc = run("board sem bloco", {"title":"x","media":media,
    "beats":[beat("a.","board"), beat("b.","media")]})
assert "board" not in [b["layout"] for b in sc["beats"]] and sc["board"] is None

# 5) bloco board inválido (1 item) -> descartado
sc = run("board com 1 item", {"title":"x","media":media,"board":{"items":[{"label":"só um"}]},
    "beats":[beat("a.","media")]})
assert sc["board"] is None

# 6) cena antiga (sem board) continua igual
sc = run("cena antiga", {"title":"x","media":media,"beats":[beat("a.","media"), beat("b.","title")]})
assert sc["board"] is None and sc["beats"][0]["callouts"]

# 7) fallback e contagem de blocos
fb = S.fallback_scene("Olá. Teste.")
assert fb["board"] is None
print("\nvisual_blocks(com quadro) =", S.visual_blocks({"media":media,"board":board}))
print("\nTODOS OS TESTES PASSARAM")
