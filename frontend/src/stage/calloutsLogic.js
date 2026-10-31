// Chamadas de texto: quais já entraram, onde ficam e para onde apontam (lógica pura).

import { CALLOUT } from "./tuning.js";

// Faixas laterais (em % do palco) onde as chamadas ficam, fora da área de conteúdo.
export const LANE = CALLOUT.lane;
const SLOT_Y = CALLOUT.slotsY;

/** Entram conforme a fala avança: `at` é a fração do trecho em que cada uma aparece. */
export function visibleCallouts(callouts, progress, finished) {
  const list = callouts || [];
  return finished ? list : list.filter((c) => progress >= c.at);
}

/** Altura (em % do palco) de cada chamada: as de um mesmo lado descem em fila. */
export function placeCallouts(callouts) {
  const used = { left: 0, right: 0 };
  return (callouts || []).map((c) => {
    const side = c.side === "right" ? "right" : "left";
    const y = SLOT_Y[used[side] % SLOT_Y.length] + (used[side] >= SLOT_Y.length ? 6 : 0);
    used[side] += 1;
    return { ...c, side, y };
  });
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * Ponto para onde a linha da chamada aponta (em % do palco): a borda do cartão de mídia citado,
 * o centro de um nó do diagrama ou, sem alvo, o cartão em destaque (ou o centro do palco).
 */
export function anchorFor(callout, ctx) {
  const { cards = [], nodes = {} } = ctx;
  const side = callout.side;
  const card = cards.find((k) => k.id === callout.target) || (callout.target ? null : cards.find((k) => k.featured) || cards[0]);
  if (card) {
    return { x: side === "left" ? card.x : card.x + card.w, y: clamp(callout.y, card.y + 3, card.y + card.h - 3) };
  }
  const node = callout.target && nodes[callout.target];
  if (node) return { x: node.x, y: node.y };
  return CALLOUT.defaultAnchor;
}
