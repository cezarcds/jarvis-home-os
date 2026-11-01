// Todos os números da coreografia da cena num lugar só: posições, ritmo e tamanhos.
// (Os tempos das animações CSS estão no topo do bloco ".hud" em src/index.css e em ".st" em stage/stage.css.)

// Áreas do palco, em % da tela. O conteúdo fica na faixa central (x 18%–82%); as laterais são das chamadas.
export const AREAS = {
  band: { x: 18, y: 9, w: 64, h: 76 },        // mural ou diagrama sozinho
  halfLeft: { x: 18, y: 9, w: 31, h: 76 },    // layout "split": mural à esquerda
  halfRight: { x: 50, y: 9, w: 32, h: 76 },   // layout "split": diagrama, gráfico ou mapa à direita
  strip: { x: 70.5, y: 9, w: 11.5, h: 76 },   // layout "diagram": coluna de miniaturas
  diagramWithStrip: { x: 18, y: 9, w: 51, h: 76 },
  board: { x: 16, y: 9, w: 68, h: 76 },        // layout "board": quadro negro desenhado
  titleWallOpacity: 0.55,                      // layout "title": o mural fica atrás do título, mais apagado
};

// Mural de mídia (cartões flutuantes)
export const WALL = {
  max: 4,            // cartões ao mesmo tempo
  gap: 1.6,          // vão entre cartões (%)
  tilt: 2.0,         // inclinação máxima dos cartões, em graus (cartões "colados com fita")
  tiltStrip: 0.9,    // inclinação na coluna de miniaturas
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

// Quadro desenhado: traços e ícones que se desenham sobre a cena
export const MARKS = {
  wobble: 2.2,        // tremor do traço (px)
  arrowHead: 16,      // tamanho da ponta da seta (px)
  iconSize: 58,       // tamanho dos ícones (px)
  nodeW: 118,         // área aproximada de um nó do diagrama (px), para circular/sublinhar
  nodeH: 50,
  drawMs: 900,        // quanto tempo um traço leva para ser desenhado
  stagger: 260,       // intervalo entre os traços de uma mesma marca (ms)
  leaveMs: 650,
  colors: {           // cor por tipo de marca (giz e marcador)
    circle: "#fbbf24", underline: "#f5f1e4", arrow: "#8be9fd", bracket: "#f5f1e4", icon: "#8be9fd",
  },
};

// Palavra-impacto (partículas)
export const IMPACT = {
  maxParticles: 3200,
  formS: 1.15,        // tempo de formação (s)
  holdMs: 3400,       // quanto tempo a palavra fica inteira antes de se desfazer
  maxWidth: 0.7,      // fração da largura do palco que a palavra pode ocupar
  maxHeight: 0.34,
  font: '"Permanent Marker", "Segoe Print", Impact, sans-serif',
  colors: { neutral: "#c9f6ff", alert: "#ffc94d", positive: "#7ff0c2" },
};
