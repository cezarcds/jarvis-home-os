import React, { useMemo, useState } from "react";
import { Icon } from "./icons.jsx";
import { useSize } from "./useSize.js";

const KIND_COLOR = {
  source: "#fbbf24", process: "#67e8f9", store: "#a78bfa",
  output: "#34d399", actor: "#f9a8d4", concept: "#7dd3fc", hazard: "#fb7185",
};

function edgeGeometry(a, b, r, bend) {
  const dx = b.px - a.px, dy = b.py - a.py;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const s = { x: a.px + ux * (r + 5), y: a.py + uy * (r + 5) };
  const e = { x: b.px - ux * (r + 11), y: b.py - uy * (r + 11) };
  const mx = (s.x + e.x) / 2, my = (s.y + e.y) / 2;
  const cx = mx - uy * len * bend, cy = my + ux * len * bend;
  const t = 0.5;
  const mid = { x: (1 - t) * (1 - t) * s.x + 2 * (1 - t) * t * cx + t * t * e.x, y: (1 - t) * (1 - t) * s.y + 2 * (1 - t) * t * cy + t * t * e.y };
  // direção final (tangente) para a ponta da seta
  const tx = e.x - cx, ty = e.y - cy, tl = Math.hypot(tx, ty) || 1;
  return { d: `M${s.x},${s.y} Q${cx},${cy} ${e.x},${e.y}`, s, e, mid, dir: { x: tx / tl, y: ty / tl } };
}

export default function DiagramLayer({ diagram, revealed, focus, active }) {
  const [ref, { w, h }] = useSize();
  const [selected, setSelected] = useState(null);

  const r = Math.max(22, Math.min(40, Math.min(w, h) * 0.075));
  const focusSet = useMemo(() => new Set(focus), [focus]);
  const hasFocus = focusSet.size > 0;

  const nodes = useMemo(() => {
    const out = {};
    diagram.nodes.forEach((n) => (out[n.id] = { ...n, px: (n.x / 100) * w, py: (n.y / 100) * h }));
    return out;
  }, [diagram, w, h]);

  const visibleNodes = diagram.nodes.filter((n) => revealed.has(n.id));
  const visibleEdges = diagram.edges.filter((e) => revealed.has(e.from) && revealed.has(e.to));

  // Câmera: com exatamente 1 nó em foco, aproxima suavemente nele, mas só o
  // quanto couber SEM cortar nenhum nó já revelado (nem seus rótulos).
  let camera = { transform: "translate(0px,0px) scale(1)" };
  if (active && focus.length === 1 && nodes[focus[0]] && w && visibleNodes.length) {
    const xs = visibleNodes.map((n) => nodes[n.id].px), ys = visibleNodes.map((n) => nodes[n.id].py);
    const minX = Math.min(...xs) - r - 24, maxX = Math.max(...xs) + r + 24;
    const minY = Math.min(...ys) - r - 14, maxY = Math.max(...ys) + r + 96; // espaço do rótulo e do detalhe
    const s = Math.min(1.25, w / Math.max(1, maxX - minX), h / Math.max(1, maxY - minY));
    if (s >= 1.04) {
      const f = nodes[focus[0]];
      const tx = Math.max(-minX * s, Math.min(w - maxX * s, w / 2 - f.px * s));
      const ty = Math.max(-minY * s, Math.min(h - maxY * s, h / 2 - f.py * s));
      camera = { transform: `translate(${tx}px,${ty}px) scale(${s})` };
    }
  }

  return (
    <div className="dg" ref={ref}>
      {w > 0 && (
        <div className="dg-camera" style={camera}>
          <svg className="dg-wires" width={w} height={h} aria-hidden="true">
            {visibleEdges.map((e, i) => {
              const a = nodes[e.from], b = nodes[e.to];
              const g = edgeGeometry(a, b, r, i % 2 ? 0.09 : -0.09);
              const lit = hasFocus && (focusSet.has(e.from) || focusSet.has(e.to));
              const dim = hasFocus && !lit;
              const color = KIND_COLOR[a.kind] || KIND_COLOR.concept;
              return (
                <g key={`${e.from}>${e.to}`} className={`dg-edge ${lit ? "is-lit" : ""} ${dim ? "is-dim" : ""}`} style={{ color }}>
                  <path className="dg-edge-glow" d={g.d} pathLength="1" />
                  <path className="dg-edge-line" d={g.d} pathLength="1" />
                  <path className="dg-arrowhead" d="M-9,-5 L2,0 L-9,5 z" transform={`translate(${g.e.x + g.dir.x * 6},${g.e.y + g.dir.y * 6}) rotate(${(Math.atan2(g.dir.y, g.dir.x) * 180) / Math.PI})`} />
                  {e.flow && [0, 1, 2].map((k) => (
                    <circle key={k} r={lit ? 3.4 : 2.6} className="dg-particle">
                      <animateMotion dur={lit ? "1.6s" : "2.8s"} begin={`${k * (lit ? 0.53 : 0.93)}s`} repeatCount="indefinite" path={g.d} />
                    </circle>
                  ))}
                  {e.label && (
                    <text x={g.mid.x} y={g.mid.y - 7} className="dg-edge-label" textAnchor="middle">{e.label}</text>
                  )}
                </g>
              );
            })}
          </svg>

          {visibleNodes.map((n) => {
            const p = nodes[n.id];
            const isFocus = focusSet.has(n.id);
            const showDetail = (isFocus || selected === n.id) && n.detail;
            const color = KIND_COLOR[n.kind] || KIND_COLOR.concept;
            return (
              <button
                key={n.id}
                type="button"
                className={`dg-node ${isFocus ? "is-focus" : ""} ${hasFocus && !isFocus ? "is-dim" : ""}`}
                style={{ left: p.px, top: p.py, "--c": color, "--r": `${r}px` }}
                onClick={() => setSelected((s) => (s === n.id ? null : n.id))}
              >
                <span className="dg-disc">
                  {isFocus && <i className="dg-ring" />}
                  <Icon name={n.icon} kind={n.kind} size={r * 0.95} />
                </span>
                <span className="dg-text">
                  <span className="dg-label">{n.label}</span>
                  {showDetail && <span className="dg-detail">{n.detail}</span>}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
