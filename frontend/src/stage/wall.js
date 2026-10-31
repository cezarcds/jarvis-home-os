// Mural de mídia: várias imagens/vídeos ao mesmo tempo, em grade "editorial" (um destaque grande
// e os outros menores). Matemática pura (sem React), em % da área do mural.

import { WALL } from "./tuning.js";

export const MAX_WALL = WALL.max;
const G = WALL.gap;

const stackV = (x, w, n, y0 = 0, h = 100) => {
  const ch = (h - G * (n - 1)) / n;
  return Array.from({ length: n }, (_, i) => [x, y0 + i * (ch + G), w, ch]);
};
const stackH = (y, h, n, x0 = 0, w = 100) => {
  const cw = (w - G * (n - 1)) / n;
  return Array.from({ length: n }, (_, i) => [x0 + i * (cw + G), y, cw, h]);
};

/** Encaixes [x, y, w, h] (0..100) para n cartões; o encaixe 0 é o do destaque (o maior). */
export function slotsFor(n, mode = "full") {
  n = Math.max(1, Math.min(MAX_WALL, n));
  if (n === 1) return [[0, 0, 100, 100]];
  if (mode === "strip") return stackV(0, 100, n);
  if (mode === "half") {
    if (n === 2) return stackV(0, 100, 2);
    const top = (100 - G) / 2;
    if (n === 3) return [[0, 0, 100, top], ...stackH(top + G, top, 2)];
    return [...stackH(0, top, 2), ...stackH(top + G, top, 2)];
  }
  if (n === 2) return stackH(0, 100, 2);
  if (n === 3) return [[0, 0, 58, 100], ...stackV(58 + G, 42 - G, 2)];
  return [[0, 0, 56, 100], ...stackV(56 + G, 44 - G, 3)];
}

const clampN = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * Posiciona os cartões dentro da área do mural (em % do palco).
 * `ids` mantém a ordem original (cada cartão conserva a identidade, então a mudança de grade vira
 * uma transição suave); o `featured` ocupa o maior encaixe.
 */
export function placeWall(ids, featured, area) {
  const list = ids.slice(0, MAX_WALL);
  if (!list.length || !area || area.w <= 0) return [];
  const slots = slotsFor(list.length, area.mode || "full");
  const fi = Math.max(0, list.indexOf(featured));
  const order = [fi, ...list.map((_, i) => i).filter((i) => i !== fi)];
  const slotOf = {};
  order.forEach((idx, k) => { slotOf[idx] = slots[k]; });
  const tilt = area.mode === "strip" ? WALL.tiltStrip : WALL.tilt;
  return list.map((id, i) => {
    const [sx, sy, sw, sh] = slotOf[i];
    return {
      id,
      featured: i === fi && list.length > 1,
      x: area.x + (sx * area.w) / 100,
      y: area.y + (sy * area.h) / 100,
      w: (sw * area.w) / 100,
      h: (sh * area.h) / 100,
      rot: Number((((i * 37) % 7) - 3) * (tilt / 3)).toFixed(2) * 1,
      delay: i * WALL.delayStepMs,
      float: WALL.floatBaseS + (i % 3) * WALL.floatStepS,
    };
  });
}

/** Quais mídias aparecem neste beat: as do `show` (ou todas) que existem ou ainda estão carregando. */
export function wallIds(scene, beat, entries) {
  const all = (scene?.media || []).map((m) => m.id);
  const wanted = beat?.show?.length ? beat.show.filter((id) => all.includes(id)) : all;
  const alive = (id) => entries[id] && entries[id].status !== "none";
  let ids = wanted.filter(alive);
  if (!ids.length) ids = all.filter(alive); // o que o beat pediu não existe: usa o que tiver
  return ids.slice(0, MAX_WALL);
}

export const clampPct = clampN;
