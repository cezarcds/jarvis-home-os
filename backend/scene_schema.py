"""Validação e saneamento do roteiro de cena gerado pelo LLM.

O modelo é o "diretor": ele devolve um JSON com mídia, diagrama, gráfico,
pontos geográficos e uma lista de "beats" (trechos de fala + instruções
visuais). Este módulo garante que o front-end só receba dados seguros e
bem formados, e corrige o que o LLM costuma errar (coordenadas sobrepostas,
ids quebrados, arestas órfãs, textos enormes).

Só usa a biblioteca padrão, para poder ser testado sem dependências.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

LAYOUTS = {"title", "media", "diagram", "split", "chart", "eye"}
NODE_KINDS = {"source", "process", "store", "output", "actor", "concept", "hazard"}
ICONS = {
    "atom", "bolt", "flame", "drop", "gear", "fan", "cloud", "sun", "wind",
    "cell", "dna", "brain", "heart", "globe", "building", "factory", "chip",
    "database", "network", "lock", "rocket", "planet", "book", "scale", "coin",
    "chart", "person", "leaf", "thermo", "magnet", "wave", "flask", "pipe",
    "shield", "clock", "eye", "pin",
}
CHART_TYPES = {"bar", "line"}
MEDIA_KINDS = {"image", "video"}

MAX_BEATS = 8
MAX_NODES = 12
MAX_EDGES = 18
MAX_MEDIA = 3
MAX_POINTS = 14
MAX_SERIES = 10

_ID_RE = re.compile(r"[^a-z0-9_]+")


def _s(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _num(value: Any, lo: float, hi: float, default: float | None = None):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(n) or math.isinf(n):
        return default
    return max(lo, min(hi, n))


def _slug(value: Any, fallback: str) -> str:
    base = _ID_RE.sub("_", _s(value, 40).lower()).strip("_")
    return base or fallback


def extract_json(raw: str) -> dict:
    """Extrai o primeiro objeto JSON de uma resposta de LLM (com ou sem cercas)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("Nenhum objeto JSON encontrado")
    return json.loads(text[start : end + 1])


# --------------------------------------------------------------------------
# Layout automático do diagrama
# --------------------------------------------------------------------------

def _layered_layout(nodes: list[dict], edges: list[dict]) -> None:
    """Posiciona nós em colunas pela profundidade no grafo (esq. → dir.)."""
    ids = [n["id"] for n in nodes]
    incoming = {i: 0 for i in ids}
    out: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        out[e["from"]].append(e["to"])
        incoming[e["to"]] += 1

    depth = {i: 0 for i in ids}
    queue = [i for i in ids if incoming[i] == 0] or [ids[0]]
    seen = set(queue)
    while queue:
        cur = queue.pop(0)
        for nxt in out[cur]:
            if nxt not in seen:
                depth[nxt] = depth[cur] + 1
                seen.add(nxt)
                queue.append(nxt)
    for i in ids:  # nós desconectados vão para o fim, em ordem
        if i not in seen:
            depth[i] = max(depth.values()) + 1

    cols: dict[int, list[dict]] = {}
    for n in nodes:
        cols.setdefault(depth[n["id"]], []).append(n)
    ncols = max(cols) + 1
    for d, col in cols.items():
        x = 50.0 if ncols == 1 else 10 + 80 * d / (ncols - 1)
        for k, n in enumerate(col):
            n["x"] = round(x, 1)
            n["y"] = round(50.0 if len(col) == 1 else 18 + 64 * k / (len(col) - 1), 1)


def _resolve_overlaps(nodes: list[dict], min_dist: float = 17.0, iterations: int = 60) -> None:
    """Afasta nós que ficaram perto demais (distância medida com aspecto 16:9)."""
    aspect = 1.78
    for _ in range(iterations):
        moved = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1 :]:
                dx, dy = (b["x"] - a["x"]) * aspect, b["y"] - a["y"]
                dist = math.hypot(dx, dy)
                if dist >= min_dist:
                    continue
                if dist < 0.01:
                    dx, dy, dist = 0.5, 0.5, 0.71
                push = (min_dist - dist) / 2
                ux, uy = dx / dist, dy / dist
                a["x"] -= ux * push / aspect
                a["y"] -= uy * push
                b["x"] += ux * push / aspect
                b["y"] += uy * push
                moved = True
        for n in nodes:
            n["x"] = max(7.0, min(93.0, n["x"]))
            n["y"] = max(12.0, min(86.0, n["y"]))
        if not moved:
            break
    for n in nodes:
        n["x"], n["y"] = round(n["x"], 1), round(n["y"], 1)


# --------------------------------------------------------------------------
# Saneamento de cada parte
# --------------------------------------------------------------------------

def _clean_diagram(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list):
        return None

    nodes: list[dict] = []
    used: set[str] = set()
    for idx, rn in enumerate(raw_nodes[:MAX_NODES]):
        if not isinstance(rn, dict):
            continue
        label = _s(rn.get("label"), 28)
        if not label:
            continue
        nid = _slug(rn.get("id") or label, f"n{idx}")
        while nid in used:
            nid += "_"
        used.add(nid)
        icon = _s(rn.get("icon"), 16).lower()
        kind = _s(rn.get("kind"), 12).lower()
        nodes.append({
            "id": nid,
            "label": label,
            "detail": _s(rn.get("detail"), 110),
            "kind": kind if kind in NODE_KINDS else "concept",
            "icon": icon if icon in ICONS else None,
            "x": _num(rn.get("x"), 0, 100),
            "y": _num(rn.get("y"), 0, 100),
        })
    if len(nodes) < 2:
        return None

    ids = {n["id"] for n in nodes}
    edges: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for re_ in (raw.get("edges") if isinstance(raw.get("edges"), list) else [])[:MAX_EDGES]:
        if not isinstance(re_, dict):
            continue
        a, b = _slug(re_.get("from"), ""), _slug(re_.get("to"), "")
        if a not in ids or b not in ids or a == b or (a, b) in seen_pairs:
            continue
        seen_pairs.add((a, b))
        edges.append({
            "from": a,
            "to": b,
            "label": _s(re_.get("label"), 22),
            "flow": bool(re_.get("flow", True)),
        })

    # Se o LLM não deu coordenadas (ou deu poucas), calcula tudo automaticamente.
    if any(n["x"] is None or n["y"] is None for n in nodes):
        _layered_layout(nodes, edges)
    _resolve_overlaps(nodes)
    return {"nodes": nodes, "edges": edges}


def _clean_chart(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    series = []
    for item in (raw.get("series") if isinstance(raw.get("series"), list) else [])[:MAX_SERIES]:
        if not isinstance(item, dict):
            continue
        label, value = _s(item.get("label"), 20), _num(item.get("value"), -1e12, 1e12)
        if label and value is not None:
            series.append({"label": label, "value": value})
    if len(series) < 2:
        return None
    ctype = _s(raw.get("type"), 8).lower()
    return {
        "type": ctype if ctype in CHART_TYPES else "bar",
        "title": _s(raw.get("title"), 60),
        "unit": _s(raw.get("unit"), 12),
        "series": series,
    }


def _clean_geo(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    points, used = [], set()
    for idx, rp in enumerate((raw.get("points") if isinstance(raw.get("points"), list) else [])[:MAX_POINTS]):
        if not isinstance(rp, dict):
            continue
        lat, lon = _num(rp.get("lat"), -85, 85), _num(rp.get("lon"), -180, 180)
        label = _s(rp.get("label"), 28)
        if lat is None or lon is None or not label:
            continue
        pid = _slug(rp.get("id") or label, f"p{idx}")
        while pid in used:
            pid += "_"
        used.add(pid)
        points.append({
            "id": pid,
            "label": label,
            "detail": _s(rp.get("detail"), 110),
            "lat": lat,
            "lon": lon,
            "layer": _slug(rp.get("layer"), "geral")[:16],
        })
    if not points:
        return None
    ids = {p["id"] for p in points}
    links = []
    for rl in (raw.get("links") if isinstance(raw.get("links"), list) else [])[:MAX_EDGES]:
        if not isinstance(rl, dict):
            continue
        a, b = _slug(rl.get("from"), ""), _slug(rl.get("to"), "")
        if a in ids and b in ids and a != b:
            links.append({"from": a, "to": b, "label": _s(rl.get("label"), 22)})
    return {"points": points, "links": links}


def _clean_media(raw: Any) -> list[dict]:
    out, used = [], set()
    for idx, rm in enumerate((raw if isinstance(raw, list) else [])[:MAX_MEDIA]):
        if not isinstance(rm, dict):
            continue
        query = _s(rm.get("query"), 80)
        if len(query) < 3:
            continue
        mid = _slug(rm.get("id"), f"m{idx + 1}")
        while mid in used:
            mid += "_"
        used.add(mid)
        kind = _s(rm.get("kind"), 8).lower()
        out.append({
            "id": mid,
            "kind": kind if kind in MEDIA_KINDS else "image",
            "query": query,
            "caption": _s(rm.get("caption"), 90),
        })
    return out


def _clean_beats(raw: Any, diagram, chart, geo, media) -> list[dict]:
    node_ids = {n["id"] for n in diagram["nodes"]} if diagram else set()
    point_ids = {p["id"] for p in geo["points"]} if geo else set()
    media_ids = {m["id"] for m in media}

    beats = []
    for rb in (raw if isinstance(raw, list) else [])[:MAX_BEATS]:
        if not isinstance(rb, dict):
            continue
        say = _s(rb.get("say"), 260)
        if not say:
            continue
        layout = _s(rb.get("layout"), 10).lower()
        if layout not in LAYOUTS:
            layout = "diagram" if diagram else ("media" if media else "title")
        # Layouts impossíveis são rebaixados em vez de mostrar um palco vazio.
        if layout == "diagram" and not diagram:
            layout = "chart" if chart else ("eye" if geo else ("media" if media else "title"))
        if layout == "split" and not (diagram or chart or geo):
            layout = "media" if media else "title"
        if layout == "chart" and not chart:
            layout = "diagram" if diagram else ("eye" if geo else "title")
        if layout == "eye" and not geo:
            layout = "diagram" if diagram else "title"
        if layout in ("media", "split") and not media:
            layout = "diagram" if diagram else ("chart" if chart else ("eye" if geo else "title"))

        def pick(key, valid):
            seen, res = set(), []
            for v in (rb.get(key) if isinstance(rb.get(key), list) else []):
                s = _slug(v, "")
                if s in valid and s not in seen:
                    seen.add(s)
                    res.append(s)
            return res

        mid = _slug(rb.get("media"), "")
        beats.append({
            "say": say,
            "layout": layout,
            "caption": _s(rb.get("caption"), 40),
            "media": mid if mid in media_ids else (media[0]["id"] if media and layout in ("media", "split", "title") else None),
            "reveal": pick("reveal", node_ids | point_ids),
            "focus": pick("focus", node_ids | point_ids),
        })
    return beats


def sanitize_scene(raw: dict) -> dict:
    """Valida o JSON do diretor. Levanta ValueError se não houver cena utilizável."""
    if not isinstance(raw, dict):
        raise ValueError("Cena não é um objeto")

    diagram = _clean_diagram(raw.get("diagram"))
    chart = _clean_chart(raw.get("chart"))
    geo = _clean_geo(raw.get("geo"))
    media = _clean_media(raw.get("media"))
    beats = _clean_beats(raw.get("beats"), diagram, chart, geo, media)
    if not beats:
        raise ValueError("Cena sem beats utilizáveis")

    # Se um beat não revela nada, garante que o diagrama apareça de forma
    # progressiva: revela tudo no primeiro beat que usa o diagrama sem reveal.
    if diagram:
        all_ids = [n["id"] for n in diagram["nodes"]]
        shown = {i for b in beats for i in b["reveal"]}
        missing = [i for i in all_ids if i not in shown]
        if missing:
            for b in beats:
                if b["layout"] in ("diagram", "split"):
                    b["reveal"] = b["reveal"] + missing
                    break
            else:
                beats[-1]["reveal"] += missing
    if geo:
        all_pts = [p["id"] for p in geo["points"]]
        shown = {i for b in beats for i in b["reveal"]}
        missing = [i for i in all_pts if i not in shown]
        if missing:
            for b in beats:
                if b["layout"] == "eye":
                    b["reveal"] = b["reveal"] + missing
                    break

    return {
        "title": _s(raw.get("title"), 70) or "Explicação",
        "kind": _s(raw.get("topic_kind"), 16) or "concept",
        "media": media,
        "diagram": diagram,
        "chart": chart,
        "geo": geo,
        "beats": beats,
    }


def fallback_scene(answer: str, title: str = "Explicação") -> dict:
    """Cena mínima, só com fala, usada quando o diretor falha."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s.strip()]
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) > 260:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    beats = [
        {"say": c, "layout": "title", "caption": "", "media": None, "reveal": [], "focus": []}
        for c in chunks[:MAX_BEATS]
    ] or [{"say": answer.strip()[:420] or "Sem resposta.", "layout": "title", "caption": "", "media": None, "reveal": [], "focus": []}]
    return {"title": title, "kind": "concept", "media": [], "diagram": None, "chart": None, "geo": None, "beats": beats}
