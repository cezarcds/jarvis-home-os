// Composição adaptativa: cada layout define onde cada "painel" fica no palco
// (em % do palco). Os painéis são sempre os mesmos elementos de DOM; só mudam
// de posição/opacidade, então a transição entre layouts é um morph suave.
//
// O palco ocupa a tela inteira: só sobra uma faixa fina no topo (cabeçalho) e uma
// no rodapé (controles + legenda curta). O microfone fica num canto, fora do conteúdo.

export const HIDDEN = { x: 50, y: 50, w: 0, h: 0, o: 0 };

const FULL = { x: 2, y: 6, w: 96, h: 84, o: 1 };
const SPLIT_LEFT = { x: 2, y: 6, w: 41, h: 84, o: 1 };
const SPLIT_RIGHT = { x: 44, y: 6, w: 54, h: 84, o: 1 };

export const LAYOUT_RECTS = {
  title:   { media: { x: 0, y: 0, w: 100, h: 100, o: 1, bg: true }, diagram: HIDDEN, chart: HIDDEN, eye: HIDDEN },
  media:   { media: FULL, diagram: HIDDEN, chart: HIDDEN, eye: HIDDEN },
  diagram: { media: { x: 77, y: 8, w: 21, h: 25, o: 0.95, pip: true }, diagram: FULL, chart: HIDDEN, eye: HIDDEN },
  split:   { media: SPLIT_LEFT, diagram: SPLIT_RIGHT, chart: HIDDEN, eye: HIDDEN },
  chart:   { media: HIDDEN, diagram: HIDDEN, chart: FULL, eye: HIDDEN },
  eye:     { media: HIDDEN, diagram: HIDDEN, chart: HIDDEN, eye: { x: 0, y: 0, w: 100, h: 100, o: 1, bleed: true } },
};

/**
 * Resolve o layout efetivo de um beat conforme o que está disponível AGORA
 * (a mídia chega de forma assíncrona e pode falhar).
 */
export function effectiveLayout(beat, { hasMedia, hasDiagram, hasChart, hasGeo }) {
  const other = hasDiagram || hasChart || hasGeo;
  const alone = () => (hasDiagram ? "diagram" : hasChart ? "chart" : hasGeo ? "eye" : hasMedia ? "media" : "title");
  const l = beat.layout;
  if (l === "eye") return hasGeo ? "eye" : alone();
  if (l === "chart") return hasChart ? "chart" : alone();
  if (l === "split") return hasMedia && other ? "split" : alone();
  if (l === "media") return hasMedia ? "media" : alone();
  if (l === "diagram") return hasDiagram ? "diagram" : alone();
  return "title";
}

/**
 * Retângulos do layout. No "split" o lado direito é o diagrama, o gráfico ou o mapa
 * (o que existir), então imagem + desenho/mapa/gráfico aparecem juntos.
 * Sem mídia pronta, o diagrama ocupa a largura toda (não há miniatura).
 */
export function rectsFor(layout, { hasMedia, hasDiagram, hasChart, hasGeo } = {}) {
  const base = LAYOUT_RECTS[layout];
  if (layout === "diagram" && !hasMedia) return { ...base, media: HIDDEN };
  if (layout === "split") {
    const right = hasDiagram ? "diagram" : hasChart ? "chart" : hasGeo ? "eye" : null;
    const r = { ...base };
    if (right !== "diagram") r.diagram = HIDDEN;
    if (right) r[right] = SPLIT_RIGHT;
    return r;
  }
  return base;
}

export function rectStyle(r) {
  return {
    left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%`,
    opacity: r.o, pointerEvents: r.o > 0.5 ? "auto" : "none",
  };
}
