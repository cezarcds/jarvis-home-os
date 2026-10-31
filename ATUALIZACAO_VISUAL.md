# Atualização visual: texto vivo, tela principal enxuta e núcleo com pedestal

## O que mudou

**Tela principal**
- Saíram os painéis EVENTOS e MÍDIA RECENTE. Ficaram SISTEMA (CPU e memória reais) à esquerda e METEOROLOGIA à direita, em simetria. As mensagens que iam para EVENTOS agora vão para o console do navegador (F12).
- A resposta do Jarvis (painel de baixo, à direita) aparece palavra por palavra (`live/WordReveal.jsx`).
- Dentro do núcleo aparece o nome e o estado ("Pronto para ajudar", "Ouvindo…", "Pensando…", "Falando"), com efeito de decodificação. Embaixo do núcleo há um pedestal de luz e um feixe; a cor de tudo acompanha o estado (azul, âmbar ao ouvir).
- Fundo: brilho de horizonte que respira e vinheta. **Foto de fundo opcional:** coloque uma imagem em `frontend/public/bg.jpg` (sala ou cidade ao entardecer combina com as referências) e ela aparece por baixo de um véu escuro. Sem o arquivo, vale o gradiente.
- Os painéis ganharam um fio de luz que percorre a borda de cima de tempos em tempos.

**Cena (texto vivo, inspirado no outro projeto)**
- **Palavra-chave em partículas** (`stage/KeywordBurst.jsx`): uma palavra de impacto sai do núcleo em arcos de luz, forma as letras, segura por um instante e se dispersa. O diretor escolhe a palavra no campo `keyword` do trecho (2 ou 3 por cena). Sem `keyword`, só números das chamadas ganham esse destaque ("93 milhões de km" vira "93 MILHÕES"). No layout "title" não aparece, porque o título já ocupa o centro.
- **Chamadas que decodificam** (`live/DecodeText.jsx`): a frase surge como ruído digital e vai se resolvendo, com um brilho que atravessa o cartão ao entrar e um anel pulsando no ponto de ligação.
- **Título da cena** decodifica quando aparece.
- **Paralaxe**: cartões do mural e chamadas se mexem de leve com o mouse, cada um numa profundidade.

**Backend**
- `scene_schema.py`: novo campo `keyword` por trecho (até 2 palavras e 16 letras, limpo de pontuação).
- `main.py`: o prompt do diretor ganhou a seção PALAVRA-CHAVE.

## Onde ajustar

| O que | Onde |
|---|---|
| Tempos, tamanho e quantidade de partículas da palavra | topo de `stage/KeywordBurst.jsx` (objeto `KB`) |
| Velocidade da decodificação das chamadas | `CALLOUT.decodeMs` e `decodeDelayMs` em `stage/tuning.js` |
| Cores, pedestal, feixe e nome no núcleo | final de `index.css` (seção "Núcleo") |
| Quanto o mouse move os cartões | `--pz` em `stage/MediaWall.jsx` e `translate` em `stage/stage.css` |
| Quantas palavras-chave por cena | seção PALAVRA-CHAVE do prompt em `backend/main.py` |

Movimento reduzido no sistema (`prefers-reduced-motion`) desliga as partículas, a decodificação, a paralaxe e as animações novas.

## Arquivos

Novos: `frontend/src/live/DecodeText.jsx`, `frontend/src/live/WordReveal.jsx`, `frontend/src/stage/KeywordBurst.jsx`, `frontend/src/stage/keyword.js`, este arquivo.

Alterados: `frontend/src/App.jsx`, `frontend/src/index.css`, `frontend/src/components/SidePanels.jsx`, `frontend/src/core/HoloCore.jsx`, `frontend/src/stage/Callouts.jsx`, `frontend/src/stage/SceneStage.jsx`, `frontend/src/stage/MediaWall.jsx`, `frontend/src/stage/stage.css`, `frontend/src/stage/tuning.js`, `frontend/scripts/test-stage.mjs`, `backend/scene_schema.py`, `backend/main.py`, `backend/tests/test_cena_callouts.py`, `MOTOR_DE_CENAS.md`.

Não precisa instalar nada novo. Testes: `cd frontend && npm run test:stage` e `cd backend && pytest`.
