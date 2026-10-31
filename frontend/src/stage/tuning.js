// Todos os números da coreografia da cena num lugar só: posições, ritmo e tamanhos.
// (Os tempos das animações CSS estão no topo do bloco ".hud" em src/index.css e em ".st" em stage/stage.css.)

// Áreas do palco, em % da tela. O conteúdo fica na faixa central (x 18%–82%); as laterais são das chamadas.
export const AREAS = {
  band: { x: 18, y: 9, w: 64, h: 76 },        // mural ou diagrama sozinho
  halfLeft: { x: 18, y: 9, w: 31, h: 76 },    // layout "split": mural à esquerda
  halfRight: { x: 50, y: 9, w: 32, h: 76 },   // layout "split": diagrama, gráfico ou mapa à direita
  strip: { x: 70.5, y: 9, w: 11.5, h: 76 },   // layout "diagram": coluna de miniaturas
  diagramWithStrip: { x: 18, y: 9, w: 51, h: 76 },
  titleWallOpacity: 0.55,                      // layout "title": o mural fica atrás do título, mais apagado
};

// Mural de mídia (cartões flutuantes)
export const WALL = {
  max: 4,            // cartões ao mesmo tempo
  gap: 1.6,          // vão entre cartões (%)
  tilt: 1.1,         // inclinação máxima dos cartões, em graus
  tiltStrip: 0.5,    // inclinação na coluna de miniaturas
  delayStepMs: 90,   // intervalo entre a entrada de um cartão e o seguinte
  floatBaseS: 6,     // duração do balanço (s); cada cartão varia um pouco
  floatStepS: 1.7,
};

// Chamadas de texto
export const CALLOUT = {
  lane: {
    left: { x: 1.6, w: 15.2, edge: 17.4 },     // faixa esquerda (% do palco) e onde a linha sai do cartão
    right: { x: 83.2, w: 15.2, edge: 82.6 },
  },
  slotsY: [24, 46, 68],  // alturas (%) em que as chamadas de um mesmo lado se empilham
  leaveMs: 620,          // quanto tempo as chamadas do trecho anterior levam para sair
  defaultAnchor: { x: 50, y: 46 },
};
