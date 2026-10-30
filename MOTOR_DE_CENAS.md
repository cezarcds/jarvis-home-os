# Motor de cenas do JARVIS

Pergunta -> `/v1/scene` (LLM "diretor") -> roteiro em beats -> palco que desenha enquanto fala.

Backend (novo): `backend/scene_schema.py` (valida e autoarruma o roteiro), `backend/media.py`
(Wikimedia Commons; YouTube opcional), endpoints `/v1/scene` e `/v1/media/search` em `backend/main.py`.
Teste: `cd backend && python test_scene_schema.py`

Frontend (novo): `frontend/src/stage/` (SceneStage, DiagramLayer, MediaLayer, ChartLayer, EyeLayer,
useScenePlayer, useMediaResolver, layouts). `App.jsx` e `hooks/useSpeech.js` foram alterados.

Atalhos no palco: setas navegam, espaço pausa, Esc fecha. Tocar no núcleo interrompe e ouve a pergunta seguinte.
Mapa: tiles CARTO/OSM (troque com VITE_TILE_URL). Nenhum `npm install` novo é necessário.
