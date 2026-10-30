# Integração do Motor de Cenas na versão atual

Este pacote contém os arquivos necessários para adicionar o **Motor de Cenas**
(palco visual com beats, diagramas, mídia, gráficos e mapa) **na versão atual**
do jarvis-home-os (a que já tem rotinas, connections e SceneManager IDLE/BRIEFING/ADMIN).

## O que foi feito

### Backend
- `scene_schema.py` — validação e saneamento do roteiro do LLM
- `media.py` — busca Wikimedia Commons (+ YouTube opcional)
- `test_scene_schema.py` — testes do schema
- `main.py` — versão atual **+** endpoints `/v1/scene` e `/v1/media/search`
- `.env.example` — inclui `YOUTUBE_API_KEY` e `MEDIA_ENABLED`

### Frontend
- `src/stage/` — pasta completa (SceneStage, layers, player, resolver, CSS…)
- `src/lib/api.js` — versão atual **+** `askScene` e `searchMedia`
- `src/hooks/useSpeech.js` — versão com `speakBeat` / `cancelSpeech` (necessária pro palco)
- `src/App.jsx` — unificado:
  - Mantém rotinas, admin, briefing, IDLE
  - Ativa o palco visual automaticamente para perguntas de conhecimento
    ("como funciona…", "o que é…", "explique…", etc.)
  - Comandos de casa / rotinas continuam no fluxo `/v1/assistant`

## Como aplicar no seu projeto

1. Copie os arquivos deste pacote por cima do seu projeto (ou faça merge manual):

```bash
# a partir da raiz do seu jarvis-home-os
cp caminho/deste/pacote/backend/scene_schema.py backend/
cp caminho/deste/pacote/backend/media.py backend/
cp caminho/deste/pacote/backend/test_scene_schema.py backend/
cp caminho/deste/pacote/backend/main.py backend/          # já unificado
cp caminho/deste/pacote/backend/.env.example backend/     # ou só as linhas novas

cp -r caminho/deste/pacote/frontend/src/stage frontend/src/
cp caminho/deste/pacote/frontend/src/lib/api.js frontend/src/lib/
cp caminho/deste/pacote/frontend/src/hooks/useSpeech.js frontend/src/hooks/
cp caminho/deste/pacote/frontend/src/App.jsx frontend/src/
```

2. No `.env` do backend, opcionalmente:

```
YOUTUBE_API_KEY=sua_chave   # se quiser vídeos
MEDIA_ENABLED=true
```

3. Reinicie backend e frontend:

```bash
# backend
cd backend && source .venv/bin/activate
uvicorn main:app --reload --port 8000

# frontend
cd frontend && npm run dev
```

4. Teste o schema isolado:

```bash
cd backend && python test_scene_schema.py
```

## Atalhos no palco

- Setas: navegam entre beats
- Espaço: pausa
- Esc: fecha o modo visual
- Toque no núcleo: interrompe a narração e ouve a próxima pergunta

## Heurística no App

Perguntas que começam com “o que / como / por que / explique / me fale / quem / quando / onde / qual” (ou têm “?”) vão para o **motor de cenas**.  
O restante (rotinas, “bom dia”, comandos de casa) continua no **assistente atual**.

Você pode ajustar essa regra em `handleTranscript` em `App.jsx` se preferir sempre cena ou sempre assistente.

## Observações

- O `main.py` unificado mantém `connections` e `routines`.
- `call_groq` / `call_gemini` da versão atual são reutilizados pelo diretor de cenas.
- Nenhum pacote npm novo é necessário.
