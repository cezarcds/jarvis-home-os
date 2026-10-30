# JARVIS // Home OS

Assistente residencial com HUD holográfico.

```
jarvis-home-os/
├── backend/            FastAPI + litellm (porta 8000)
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
└── frontend/           React + Vite + Tailwind (porta 5173)
    ├── index.html, vite.config.js, tailwind.config.js, postcss.config.js
    └── src/
        ├── App.jsx            máquina de estados (STANDBY/LISTENING/PROCESSING/SPEAKING)
        ├── index.css          blueprint, vidro fosco, keyframes
        ├── lib/api.js         fetch /v1/chat/completions + clima
        ├── hooks/useSpeech.js STT + TTS pt-BR
        ├── components/        CoreRings, SidePanels, HologramCanvas
        └── scenes/            useSceneManager, SceneManager, IdleScene
```

## Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # coloque sua GEMINI_API_KEY
uvicorn main:app --reload --port 8000
```
Teste: `curl http://localhost:8000/health`

## Frontend
```bash
cd frontend
npm install
npm run dev
```
Abra http://localhost:5173 no **Chrome ou Edge** (Firefox não tem SpeechRecognition).

## Gerenciador de cena (IDLE)
- Após 45 s em STANDBY sem interação, o HUD entra em **IDLE**: holograma 3D (globo wireframe, anéis, partículas), relógio e saudação.
- Clique, toque, tecla ou mover o mouse acordam o sistema. **Alt+I** alterna IDLE/ACTIVE para testar.
- Variáveis opcionais em `frontend/.env`: `VITE_IDLE_SECONDS=45`, `VITE_OWNER_NAME=Seu Nome`.
- Novas cenas: registre o componente em `OVERLAYS` (`scenes/SceneManager.jsx`) e use `goTo("NOME")`.

## Ações, voz sem clique e visão de tela

Veja `ACOES_VOZ_E_TELA.md`. Para iniciar tudo: `iniciar_jarvis.bat`.
