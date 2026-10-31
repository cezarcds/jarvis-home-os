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

