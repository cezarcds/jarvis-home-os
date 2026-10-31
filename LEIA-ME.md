# Pacote de Notícias do Jarvis

Pesquisa de notícias na web + cartões que entram e saem + cartão de manchetes na tela principal.
Pacote **aditivo**: arquivos novos e poucas linhas nos seus arquivos. Nada do que você já tem é sobrescrito.

## O que vem aqui

```
backend/
  news/                  módulo novo (copie a pasta inteira para o seu backend/)
    intent.py            detecta pedido de notícia em pt-BR ("o que aconteceu...", "últimas do mercado", "bom dia")
    research.py          Gemini + Google Search (sua GEMINI_API_KEY) com fontes numeradas; cai para RSS se falhar
    enrich.py            abre cada fonte: título, veículo, data, imagem de capa (og:image); com proteção contra SSRF
    rss.py               Google Notícias RSS (sem chave) + feeds que você escolher
    hook.py              encaixe no chat (3 chamadas)
    router.py            GET /news/topics, GET /news/feed, POST /news/search
    config.py, cache.py, safety.py
  tests/test_news.py     22 testes da lógica pura (sem rede)
  main.patch.md          os 4 trechos para colar no main.py
  .env.news.example      variáveis novas (todas opcionais)
frontend/src/
  lib/newsApi.js
  hooks/useNewsMural.js
  components/news/       NewsMural.jsx, HeadlinesCard.jsx, news.css
  App.exemplo.jsx        exemplo com os 5 trechos marcados "[NEWS]"
```

Estrutura de pastas segue o README do projeto (`backend/` e `frontend/src/`). No GitHub existem cópias soltas
na raiz (`main.py`, `App.jsx`...), mas o que vale é o que roda na sua máquina.

## Instalação

1. Copie `backend/news/` para o seu `backend/` e `frontend/src/*` para o seu `frontend/src/`.
2. `main.py`: siga `backend/main.patch.md`. Sem dependência nova (usa `httpx`, que você já tem).
3. `App.jsx`: aplique os 5 trechos `[NEWS]` de `App.exemplo.jsx`.
4. Reinicie backend e frontend.

Opcional: copie as linhas de `.env.news.example` para o `backend/.env`.

## Como funciona

**Pesquisa (backend).** Se a fala indica notícia, o `prepare_news` roda antes do chat:
1. Gemini com Google Search responde já no tom do Jarvis, atribuindo ao veículo, citando mais de um quando
   houver e apontando divergência sem opinar. As regras estão em `NEWS_RULES` (`research.py`).
2. Cada fonte é aberta para extrair título, veículo, data e capa. Tudo em cache (10 min a pesquisa, 6 h a página).
3. Se o grounding falhar (cota, erro, sem fontes), usa o RSS de busca do Google Notícias e injeta os títulos
   como "FATOS DA PESQUISA" para o modelo de chat resumir. Se nada vier, o Jarvis diz que não conseguiu,
   em vez de inventar.
4. A resposta do chat ganha o campo `news` com os cartões. O teto é 25 s; estourou, o Jarvis segue como chat normal.

**Visual (frontend).** `NewsMural` mostra 3 cartões por trecho (capa, veículo, hora, manchete, link),
troca a cada 6 s, e fecha 9 s depois que o Jarvis termina de falar (ou no ✕). Chamadas laterais mostram o
"a seguir", com o veículo. O `HeadlinesCard` da tela principal lê o RSS direto (sem pesquisa, sem chave),
com abas por tópico e atualização a cada 10 min.

**Rotina "bom dia".** Fala que começa com "bom dia" dispara o resumo: manchetes de mercado primeiro, depois Brasil.
Se `bom dia` + pergunta específica ("bom dia, o que houve com o dólar hoje?"), vale a pergunta.
Desligue com `NEWS_BRIEFING_ON_GREETING=0`.

## Contrato dos cartões

Cada item em `news.items`:
`{ id, title, outlet, url, published (ISO UTC), image (URL ou null) }`.
Se o seu diretor de cena já monta mural/laterais, é só alimentá-lo com `news.items` (e `news.query`/`news.topic`);
o `NewsMural` aqui é um mural independente que funciona sem ele.

## Testar

```bash
cd backend && python -m unittest discover -s tests -v          # lógica, sem rede

curl "http://localhost:8000/news/feed?topic=mercado&limit=3"   # RSS
curl -X POST http://localhost:8000/news/search -H "Content-Type: application/json" \
     -d '{"query":"o que aconteceu nas eleições do Brasil no último domingo"}'
```
No Jarvis, fale: "últimas notícias do mercado", "o que aconteceu hoje com o dólar", "bom dia".
O log do backend mostra `Pesquisa com grounding: N fontes` ou o motivo do fallback.

## O que eu testei e o que não

- **Testado:** detecção de intenção (positivos e negativos), parse de RSS/Atom, metatags, proteção SSRF,
  cache, fluxo do hook (com e sem fontes), sintaxe do JS/JSX.
- **Não testado:** chamadas reais à internet, ao Gemini e ao Google Notícias (meu ambiente estava sem rede),
  nem a renderização no navegador. A primeira execução real é a sua; se algo falhar, o log do backend e o
  console do navegador dizem onde.
- Não vi o seu diretor de cena, a Wikipédia nem o mural local (o GitHub está atrás da sua versão). Por isso
  o encaixe é pelo contrato acima, e o `App.exemplo.jsx` é baseado no App público.

## Limites conhecidos

- **Cota do Google Search no Gemini** pode ser limitada na sua conta/modelo. Nesse caso o fallback RSS entra
  sozinho (resumo só a partir de títulos, sem o contexto mais profundo).
- **Capa:** é o `og:image` do veículo, não print. Itens do RSS de Google Notícias vêm sem capa (o link é um
  redirecionamento do Google) e aparecem como "SEM IMAGEM". Sites com paywall ou bloqueio a robôs também
  podem não entregar capa.
- **Divergência entre veículos** depende de o Gemini achar mais de uma fonte; está instruído a apontar, mas não
  há garantia. Em política, confira os links.
- A detecção por palavras-chave é conservadora; frases fora do padrão podem passar batido. Ajuste as listas em `intent.py`.
- Print de página (navegador real no backend) ficou de fora, como combinado.

## Ajustes rápidos

| Quer | Onde |
|---|---|
| Mais/menos cartões por trecho, tempos | constantes no topo de `hooks/useNewsMural.js` |
| Tópicos e consultas do RSS | `TOPICS` em `news/config.py` |
| Feeds próprios (InfoMoney, Valor...) | `NEWS_EXTRA_FEEDS` no `.env` |
| Tom e regras da atribuição | `NEWS_RULES` em `news/research.py` |
| Posição das chamadas laterais | `top-[38%]` em `NewsMural.jsx` |
