// Composição adaptativa: cada layout define onde cada "painel" fica no palco
// (em % do palco). Os painéis são sempre os mesmos elementos de DOM; só mudam
// de posição/opacidade, então a transição entre layouts é um morph suave.

export const HIDDEN = { x: 50, y: 50, w: 0, h: 0, o: 0 };

export const LAYOUT_RECTS = {
  title:   { media: { x: 0,  y: 0,  w: 100, h: 100, o: 1, bg: true }, diagram: HIDDEN, chart: HIDDEN, eye: HIDDEN },
  media:   { media: { x: 12, y: 14, w: 76,  h: 64,  o: 1 },           diagram: HIDDEN, chart: HIDDEN, eye: HIDDEN },
  diagram: { media: { x: 83, y: 15, w: 14,  h: 16,  o: 0.9, pip: true }, diagram: { x: 9, y: 14, w: 72, h: 68, o: 1 }, chart: HIDDEN, eye: HIDDEN },
  split:   { media: { x: 11, y: 14, w: 34,  h: 64,  o: 1 },           diagram: { x: 46, y: 13, w: 51, h: 69, o: 1 }, chart: HIDDEN, eye: HIDDEN },
  chart:   { media: HIDDEN, diagram: HIDDEN, chart: { x: 10, y: 14, w: 80, h: 64, o: 1 }, eye: HIDDEN },
  eye:     { media: HIDDEN, diagram: HIDDEN, chart: HIDDEN, eye: { x: 0, y: 0, w: 100, h: 100, o: 1, bleed: true } },
};

/**
 * Resolve o layout efetivo de um beat conforme o que está disponível AGORA
 * (a mídia chega de forma assíncrona e pode falhar).
 */
export function effectiveLayout(beat, { hasMedia, hasDiagram, hasChart, hasGeo }) {
  let l = beat.layout;
  if (l === "eye" && !hasGeo) l = hasDiagram ? "diagram" : "title";
  if (l === "chart" && !hasChart) l = hasDiagram ? "diagram" : "title";
  if (l === "split" && !hasMedia) l = hasDiagram ? "diagram" : "title";
  if (l === "media" && !hasMedia) l = hasDiagram ? "diagram" : "title";
  if (l === "diagram" && !hasDiagram) l = hasMedia ? "media" : "title";
  return l;
}

/** Retângulos do layout; sem mídia pronta, o diagrama ocupa a largura toda (não há miniatura). */
export function rectsFor(layout, hasMedia) {
  const base = LAYOUT_RECTS[layout];
  if (layout === "diagram" && !hasMedia) return { ...base, diagram: { x: 7, y: 14, w: 89, h: 68, o: 1 } };
  return base;
}

export function rectStyle(r) {
  return {
    left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%`,
    opacity: r.o, pointerEvents: r.o > 0.5 ? "auto" : "none",
  };
}
