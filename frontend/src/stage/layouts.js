// Composição do palco na tela única. O conteúdo fica numa faixa central (x 18%–82%); as laterais
// ficam livres para as chamadas de texto. Os painéis são sempre os mesmos elementos de DOM e só
// mudam de lugar/opacidade, então a troca de layout é uma transição suave.
//
import { AREAS } from "./tuning.js";

// Cada retângulo está em % do palco. `mode` diz como o mural de mídia se organiza dentro dele.

export const HIDDEN = { x: 50, y: 50, w: 0, h: 0, o: 0, mode: "full" };

const BAND = { ...AREAS.band, o: 1 };
const HALF_L = { ...AREAS.halfLeft, o: 1 };
const HALF_R = { ...AREAS.halfRight, o: 1 };
const STRIP = { ...AREAS.strip, o: 1 };
const DIAGRAM_WITH_STRIP = { ...AREAS.diagramWithStrip, o: 1 };

export const LAYOUT_RECTS = {
  title:   { media: { ...BAND, o: AREAS.titleWallOpacity, mode: "full" }, diagram: HIDDEN, chart: HIDDEN, eye: HIDDEN },
  media:   { media: { ...BAND, mode: "full" }, diagram: HIDDEN, chart: HIDDEN, eye: HIDDEN },
  diagram: { media: { ...STRIP, mode: "strip" }, diagram: DIAGRAM_WITH_STRIP, chart: HIDDEN, eye: HIDDEN },
  split:   { media: { ...HALF_L, mode: "half" }, diagram: HALF_R, chart: HIDDEN, eye: HIDDEN },
  chart:   { media: HIDDEN, diagram: HIDDEN, chart: BAND, eye: HIDDEN },
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
 * (o que existir). Sem mídia pronta, o diagrama ocupa a faixa central inteira.
 */
export function rectsFor(layout, { hasMedia, hasDiagram, hasChart, hasGeo } = {}) {
  const base = LAYOUT_RECTS[layout];
  if (layout === "diagram" && !hasMedia) return { ...base, media: HIDDEN, diagram: BAND };
  if (layout === "split") {
    const right = hasDiagram ? "diagram" : hasChart ? "chart" : hasGeo ? "eye" : null;
    const r = { ...base };
    if (right !== "diagram") r.diagram = HIDDEN;
    if (right) r[right] = HALF_R;
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
