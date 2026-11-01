# Motor de cenas do JARVIS

Pergunta -> `/v1/scene` (LLM "diretor") -> roteiro em beats -> palco que desenha enquanto fala.

Backend (novo): `backend/scene_schema.py` (valida e autoarruma o roteiro), `backend/media.py`
(Wikimedia Commons; YouTube opcional), endpoints `/v1/scene` e `/v1/media/search` em `backend/main.py`.
Teste: `cd backend && python test_scene_schema.py`

Frontend (novo): `frontend/src/stage/` (SceneStage, DiagramLayer, MediaLayer, ChartLayer, EyeLayer,
useScenePlayer, useMediaResolver, layouts). `App.jsx` e `hooks/useSpeech.js` foram alterados.

Atalhos no palco: setas navegam, espaço pausa, Esc fecha. Tocar no núcleo interrompe e ouve a pergunta seguinte.
Mapa: tiles CARTO/OSM (troque com VITE_TILE_URL). Nenhum `npm install` novo é necessário.

## Cena na tela única (mural, chamadas e núcleo que recua)

A cena não troca mais de tela: ela entra por cima do mesmo HUD. O núcleo recua (fica menor, ao fundo), os painéis
saem para os lados e para baixo, e o palco (`SceneStage`) mostra:

- **Mural de mídia** (`MediaWall`, `wall.js`): até 4 imagens e vídeos ao mesmo tempo, em cartões flutuantes. O diretor
  escolhe, em cada beat, quais ficam visíveis (`show`) e qual é a destacada (`media`). Vídeos tocam mudos em laço.
- **Chamadas de texto** (`Callouts`, `calloutsLogic.js`): frases de 2 a 6 palavras que entram pela esquerda e pela direita
  quando a fala chega no ponto `at` de cada uma (0 a 1), com uma linha até o cartão ou nó a que se referem.
  O diretor escreve as chamadas (`callouts` em cada beat); sem elas, o plano B usa os rótulos do que entra em cena.
- Diagramas, gráficos e mapa continuam como antes, na faixa central.

Ajustes: posições, tamanhos e ritmo em `frontend/src/stage/tuning.js`; tempos das animações no topo do bloco `.hud` em
`src/index.css`. Backend: `scene_schema.py` valida `callouts`/`show` e o prompt do diretor está em `main.py`.
Testes: `cd backend && pytest` e `cd frontend && npm run test:stage`.

O HUD também mostra CPU e memória reais (`GET /v1/system/stats`, precisa do `psutil`) e a mídia recente das cenas.

## Palavra-impacto e quadro desenhado

- **Palavra-impacto** (`ImpactWord`, `particles.js`): o diretor escolhe uma palavra (no máximo duas) por trecho, em `impact`
  (`text`, `at`, `tone`). No ponto da fala em que ela é citada, ela se forma de partículas no centro da tela, fica inteira por
  alguns segundos e se desfaz. Nunca aparece em dois trechos seguidos. A fonte é de marcador (Permanent Marker).
- **Marcas desenhadas** (`Marks`, `handDrawn.js`, `icons.js`): `marks` de cada trecho (círculo, sublinhado, seta, colchete e
  ícone). Os traços têm tremor de mão, são determinísticos e se desenham no ritmo da fala; o rótulo usa letra de mão (Caveat).
  Uma marca cujo alvo não está visível naquele momento (mídia fora do mural, nó ainda não revelado) não é desenhada.
- **Ícones:** 35 ícones de traço fino em `frontend/src/stage/icons.js`. A lista tem de ser igual a `MARK_ICONS` em
  `backend/scene_schema.py` (um teste confere). Para acrescentar um, inclua nos dois e no prompt do diretor.
- **Cartões:** moldura de papel, fita adesiva e inclinação leve; cada mídia pode ter um `tag` que aparece na vertical.
- Ajustes: `AREAS`, `WALL`, `CALLOUT`, `MARKS` e `IMPACT` em `frontend/src/stage/tuning.js` (cores, tempos, tamanhos).
- As fontes vêm do Google Fonts (`index.html`); sem internet caem nas fontes do sistema.

