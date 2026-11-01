# JARVIS // Home OS

Assistente residencial com HUD holográfico: voz livre ("Jarvis, ..."), rotinas, notícias e **cenas visuais** (o Jarvis explica com imagens, vídeos, diagramas, mapas e gráficos enquanto fala).

> Este README foi reescrito a partir do código real. Itens marcados com ⚠ não foram revisados.

## Estrutura

```
backend/                     FastAPI (porta 8000)
├── main.py                  chat, diretor de cenas (/v1/scene), busca de mídia
├── connections/             integrações (e-mail, agenda...) e ferramentas
├── routines/                rotinas (CRUD + execução)
├── actions/                 ações no computador, visão de tela, HUD
├── voice/                   voz livre (faster-whisper, WebSocket)
├── news/                    notícias (RSS + cena de cartões)
├── media.py, grounding.py   busca de imagens/vídeos e fatos de referência
├── scene_schema.py          valida/limpa o JSON do diretor de cenas       ⚠
└── sysinfo.py               CPU/memória (/v1/system/stats)

frontend/src/                React + Vite + Tailwind (porta 5173)
├── App.jsx                  máquina de estados do HUD (STANDBY/LISTENING/PROCESSING/SPEAKING)
├── index.css                visual do HUD e coreografia "cena" (variáveis --core-*, --away-*)
├── core/                    núcleo 3D (CoreOrb) e nível de voz                ⚠
├── components/              CoreRings (mic compacto), SidePanels, NavRail,
│                            HologramCanvas (idle), ChalkBoard (quadro negro)
├── scenes/                  SceneManager + useSceneManager (IDLE / BRIEFING / ADMIN)
│                            IdleScene, BriefingScene, AdminScene
├── stage/                   PALCO das cenas visuais (SceneStage, player, mídia)   ⚠
├── hooks/                   useSpeech (STT/TTS), useHandsFree                     ⚠
└── lib/                     api.js, localIntents.js                               ⚠
```

## Como as telas funcionam

Há **dois sistemas de cena**, e é importante não confundi-los:

| | O que é | Onde |
|---|---|---|
| **Overlays** | telas cheias que *substituem* o HUD: `IDLE`, `BRIEFING`, `ADMIN` | `scenes/` |
| **Cena visual (palco)** | o HUD continua montado; os painéis saem, o núcleo some e o palco entra | `stage/` + `data-phase="scene"` em `index.css` |

Regra: **uma coisa de cada vez.** Abrir um overlay fecha a cena visual (`goTo` no `App.jsx`).

A cena visual vem do **diretor** (`/v1/scene`): o LLM devolve um roteiro (`beats`) com fala, mídia, diagrama, mapa, gráfico, chamadas (`callouts`), palavra-impacto (`impact`) e marcas desenhadas (`marks`).

## Rodar

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # GROQ_API_KEY e/ou GEMINI_API_KEY
uvicorn main:app --reload --port 8000
curl http://localhost:8000/health

# frontend
cd frontend
npm install
npm run dev                  # http://localhost:5173  (Chrome ou Edge)
```

Variáveis do backend: `GROQ_API_KEY`, `GROQ_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL` (use um modelo que exista, ex.: `gemini-3.6-flash`), `SCENE_ORDER` (padrão `groq,gemini`).
Variáveis do frontend (`frontend/.env`): `VITE_API_URL`, `VITE_IDLE_SECONDS=45`, `VITE_BRIEFING_SECONDS=180`, `VITE_OWNER_NAME`.

## Atalhos

`Alt+I` alterna IDLE/ACTIVE · `Alt+R` abre/fecha rotinas · `Esc` fecha a cena visual.

## Estado dos módulos

| Módulo | Estado |
|---|---|
| Chat com fallback Groq → Gemini | funciona (confira `GEMINI_MODEL`) |
| Rotinas e painel admin | funciona |
| Voz push-to-talk (Web Speech) | funciona em Chrome/Edge |
| Voz livre (faster-whisper) | depende de instalação ⚠ |
| Notícias (cartões via `/v1/scene`) | funciona ⚠ |
| Cenas visuais (palco) | ⚠ ver `docs/MELHORIAS.md` |
| Quadro negro desenhado (layout `board`) | novo, integrado ao palco e ao diretor |

## Contribuindo

Uma branch por pessoa/assunto, PR pequeno, mensagem de commit dizendo *o quê* e *por quê*. Nunca commite `.env`.
