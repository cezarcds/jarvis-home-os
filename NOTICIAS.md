# Notícias no Jarvis (pacote adaptado ao projeto atual)

## Como funciona agora
Pedir notícias vira uma **cena do palco**: o Jarvis pesquisa fontes reais, fala o resumo citando os veículos e mostra um mural de cartões (capa, veículo, hora, manchete). Clicar na manchete não é necessário; os links ficam nos dados da cena.

Dois caminhos, os dois chamam `news/scene.py`:
- **`/v1/scene`** (perguntas como "o que aconteceu hoje com o dólar?"): o hook roda antes do diretor.
- **`/v1/assistant`** (pedidos como "últimas notícias do mercado"): o hook roda depois das ações, rotinas e gatilhos (a sua rotina "Bom dia" continua com prioridade) e antes do roteamento por LLM. Devolve `kind: "noticias"` com `news_scene`.

Pesquisa: Gemini com Google Search (usa a sua GEMINI_API_KEY). Sem isso, cai no RSS do Google Notícias e o resumo é feito pelo `llm.py` (na ordem do seu `LLM_ORDER`). Se nenhum modelo responder, o Jarvis fala as manchetes como vieram.

Na tela principal, o cartão **MANCHETES** (RSS, sem chave) fica abaixo do painel Sistema.

## Copiar
Cole por cima, mantendo as pastas. Reinicie o backend. No frontend, se rodar o build, refaça o `dist`.
Acrescente ao `backend/.env` o que quiser de `backend/.env.news.example` (tudo opcional).

## Apagar (sobras que não são mais usadas)
- `LEIA-ME.md` do pacote, se você o copiou para a raiz
- `backend/main.patch.md`
- `frontend/src/App.exemplo.jsx`
- `frontend/src/components/news/NewsMural.jsx`
- `frontend/src/hooks/useNewsMural.js`
- Do pacote visual que você reverteu: `ATUALIZACAO_VISUAL.md`, `frontend/src/live/DecodeText.jsx`, `frontend/src/live/WordReveal.jsx`, `frontend/src/stage/KeywordBurst.jsx`, `frontend/src/stage/keyword.js`

## Limites
- Perguntas de continuação dentro da cena de notícias ("e o dólar?") vão para o diretor normal; só um pedido claramente de notícias refaz a pesquisa.
- `NEWS_BRIEFING_ON_GREETING` não faz efeito enquanto sua rotina "Bom dia" existir (ela responde antes).
- A pesquisa com Google Search depende do modelo Gemini e da cota da sua chave; sem ela, usa RSS.
- As capas vêm do `og:image` da matéria; quando não há, o cartão mostra só texto.
- Não consegui rodar o build do Vite nem o FastAPI aqui: testei a lógica do backend (40 testes) e a sintaxe do frontend. Teste uma vez: `cd backend && pytest` e peça "últimas notícias do mercado".
- Dica: `useMediaResolver.js` importa `./mediaPick.js`, mas o arquivo se chama `Mediapick.js`. Funciona no Windows; quebra em Linux/Mac.
