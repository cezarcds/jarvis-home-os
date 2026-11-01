// Traço "feito à mão": geometria pura (sem React) para círculos, sublinhados, setas, colchetes e ícones
// que se desenham sobre a cena. Tudo em pixels do palco, com ruído determinístico (mesma cena = mesmo traço).

import { MARKS } from "./tuning.js";

export function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const r1 = (n) => Math.round(n * 10) / 10;

/** Curva suave (Catmull-Rom → Bézier) passando pelos pontos. */
export function smoothPath(pts) {
  if (pts.length < 2) return "";
  let d = `M${r1(pts[0][0])} ${r1(pts[0][1])}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] || p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${r1(c1[0])} ${r1(c1[1])} ${r1(c2[0])} ${r1(c2[1])} ${r1(p2[0])} ${r1(p2[1])}`;
  }
  return d;
}

/** Círculo riscado à mão: dá um pouco mais de uma volta e termina passando do começo. */
export function roughEllipse(cx, cy, rx, ry, seed) {
  const rand = rng(seed);
  const steps = 30;
  const start = rand() * Math.PI * 2;
  const pts = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const ang = start + t * 1.14 * Math.PI * 2;
    const wob = 1 + (rand() - 0.5) * 0.06 + 0.07 * t; // espirala para fora: o final não encosta no começo
    pts.push([cx + Math.cos(ang) * rx * wob, cy + Math.sin(ang) * ry * wob]);
  }
  return smoothPath(pts);
}

/** Linha com leve tremor, como traço de giz. */
export function roughLine(x1, y1, x2, y2, seed, wobble = MARKS.wobble) {
  const rand = rng(seed);
  const len = Math.hypot(x2 - x1, y2 - y1) || 1;
  const nx = -(y2 - y1) / len;
  const ny = (x2 - x1) / len;
  const segs = Math.max(3, Math.round(len / 60));
  const pts = [];
  for (let i = 0; i <= segs; i++) {
    const t = i / segs;
    const off = i === 0 || i === segs ? 0 : (rand() - 0.5) * 2 * wobble;
    pts.push([x1 + (x2 - x1) * t + nx * off, y1 + (y2 - y1) * t + ny * off]);
  }
  return smoothPath(pts);
}

/** Seta curva de a → b, com a ponta feita de dois traços. Devolve { shaft, head }. */
export function roughArrow(a, b, seed) {
  const rand = rng(seed);
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const bend = (rand() > 0.5 ? 1 : -1) * Math.min(60, len * 0.18);
  const c = [(a[0] + b[0]) / 2 + (-dy / len) * bend, (a[1] + b[1]) / 2 + (dx / len) * bend];
  const mid = (t) => [
    (1 - t) * (1 - t) * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0],
    (1 - t) * (1 - t) * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1],
  ];
  const pts = [];
  for (let i = 0; i <= 10; i++) pts.push(mid(i / 10));
  const shaft = smoothPath(pts);
  // direção de chegada para encaixar a ponta
  const tail = mid(0.92);
  const ang = Math.atan2(b[1] - tail[1], b[0] - tail[0]);
  const hl = MARKS.arrowHead;
  const spread = 0.5;
  const h1 = [b[0] - Math.cos(ang - spread) * hl, b[1] - Math.sin(ang - spread) * hl];
  const h2 = [b[0] - Math.cos(ang + spread) * hl, b[1] - Math.sin(ang + spread) * hl];
  const head = `M${r1(h1[0])} ${r1(h1[1])}L${r1(b[0])} ${r1(b[1])}L${r1(h2[0])} ${r1(h2[1])}`;
  return { shaft, head };
}

/** Colchete "[" ou "]" cobrindo a altura de `rect`. side: "left" | "right". */
export function roughBracket(rect, side, seed) {
  const rand = rng(seed);
  const pad = 14;
  const arm = 10;
  const x = side === "left" ? rect.x - pad : rect.x + rect.w + pad;
  const dir = side === "left" ? 1 : -1;
  const y1 = rect.y - 4 + (rand() - 0.5) * 3;
  const y2 = rect.y + rect.h + 4 + (rand() - 0.5) * 3;
  const pts = [[x + dir * arm, y1], [x + (rand() - 0.5), y1 + 2], [x + (rand() - 0.5) * 2, (y1 + y2) / 2], [x + (rand() - 0.5), y2 - 2], [x + dir * arm, y2]];
  return { d: smoothPath(pts), x, y1, y2 };
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * Retângulo (px) de um alvo: cartão de mídia (posição em % do palco) ou nó do diagrama (centro em %).
 * Devolve null se o alvo não está visível agora, e a marca simplesmente não é desenhada.
 */
export function targetRect(id, ctx) {
  const { cards = [], nodes = {}, size } = ctx;
  const c = cards.find((k) => k.id === id);
  if (c) return { x: (c.x * size.w) / 100, y: (c.y * size.h) / 100, w: (c.w * size.w) / 100, h: (c.h * size.h) / 100, kind: "card" };
  const n = nodes[id];
  if (n) {
    const w = MARKS.nodeW;
    const h = MARKS.nodeH;
    return { x: (n.x * size.w) / 100 - w / 2, y: (n.y * size.h) / 100 - h / 2, w, h, kind: "node" };
  }
  return null;
}

const center = (r) => [r.x + r.w / 2, r.y + r.h / 2];

/** Ponto na borda de `rect` na direção de `from` (com folga), para a seta encostar no alvo sem entrar nele. */
function edgePoint(rect, from, gap = 8) {
  const [cx, cy] = center(rect);
  const dx = from[0] - cx;
  const dy = from[1] - cy;
  const sx = Math.abs(dx) / (rect.w / 2 + gap) || 0;
  const sy = Math.abs(dy) / (rect.h / 2 + gap) || 0;
  const k = Math.max(sx, sy) || 1;
  return [cx + dx / k, cy + dy / k];
}

/**
 * Geometria de uma marca. Devolve
 *   { paths: [{ d, role: "main"|"head" }], icon?: {name,x,y,size}, label?: {text,x,y,rot,anchor} }
 * ou null quando algum alvo não está visível.
 */
export function markGeometry(mark, ctx, key = "") {
  const { size } = ctx;
  const seed = hashStr(`${key}:${mark.type}:${mark.target || ""}:${(mark.targets || []).join(",")}:${mark.at}`);
  const label = (x, y, extra = {}) => (mark.label ? { text: mark.label, x: clamp(x, 8, size.w - 8), y: clamp(y, 18, size.h - 8), rot: 0, anchor: "start", ...extra } : undefined);

  if (mark.type === "circle") {
    const r = targetRect(mark.target, ctx);
    if (!r) return null;
    const [cx, cy] = center(r);
    const rx = r.kind === "node" ? r.w * 0.62 : r.w / 2 + 12;
    const ry = r.kind === "node" ? r.h * 0.95 : r.h / 2 + 10;
    return { paths: [{ d: roughEllipse(cx, cy, rx, ry, seed), role: "main" }], label: label(cx + rx * 0.55, cy - ry - 6, { rot: -4 }) };
  }

  if (mark.type === "underline") {
    const r = targetRect(mark.target, ctx);
    if (!r) return null;
    const y = r.y + r.h + (r.kind === "node" ? 4 : 12);
    const x1 = r.x + 6;
    const x2 = r.x + r.w - 6;
    return {
      paths: [{ d: roughLine(x1, y, x2, y + 2, seed), role: "main" }, { d: roughLine(x1 + 10, y + 7, x2 - 18, y + 8, seed + 1), role: "main" }],
      label: label((x1 + x2) / 2, y + 30, { anchor: "middle", rot: -2 }),
    };
  }

  if (mark.type === "arrow") {
    const to = targetRect(mark.target, ctx);
    if (!to) return null;
    let start;
    if (mark.from) {
      const fr = targetRect(mark.from, ctx);
      if (!fr) return null;
      start = edgePoint(fr, center(to), 6);
    } else {
      const left = center(to)[0] < size.w / 2; // sem origem: a seta entra pelo lado mais próximo
      start = [left ? size.w * 0.19 : size.w * 0.81, clamp(center(to)[1] - 40, 40, size.h - 60)];
    }
    const end = edgePoint(to, start, 10);
    const { shaft, head } = roughArrow(start, end, seed);
    const mx = (start[0] + end[0]) / 2;
    const my = (start[1] + end[1]) / 2;
    return { paths: [{ d: shaft, role: "main" }, { d: head, role: "head" }], label: label(mx, my - 12, { anchor: "middle", rot: -3 }) };
  }

  if (mark.type === "bracket") {
    const rects = (mark.targets || []).map((id) => targetRect(id, ctx));
    if (rects.some((r) => !r) || rects.length < 2) return null;
    const x1 = Math.min(...rects.map((r) => r.x));
    const y1 = Math.min(...rects.map((r) => r.y));
    const x2 = Math.max(...rects.map((r) => r.x + r.w));
    const y2 = Math.max(...rects.map((r) => r.y + r.h));
    const union = { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
    const side = (x1 + x2) / 2 > size.w / 2 ? "right" : "left";
    const b = roughBracket(union, side, seed);
    const lx = side === "left" ? b.x - 22 : b.x + 24;
    return { paths: [{ d: b.d, role: "main" }], label: label(lx, (b.y1 + b.y2) / 2, { anchor: "middle", rot: -90, big: true }) };
  }

  if (mark.type === "icon") {
    const r = targetRect(mark.target, ctx);
    if (!r) return null;
    const s = MARKS.iconSize;
    const x = clamp(r.x - s * 0.15, 6, size.w - s - 6);
    const y = clamp(r.y - s * 0.95, 6, size.h - s - 6);
    return { paths: [], icon: { name: mark.icon, x, y, size: s }, label: label(x + s + 6, y + s * 0.62, { rot: -3 }) };
  }
  return null;
}
