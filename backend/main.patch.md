# Alterações no seu main.py (4 trechos pequenos)

Baseado no main.py público. Se o seu local for diferente, aplique a mesma ideia: o módulo
`news` só precisa de 3 chamadas no fluxo do chat.

## 1) Imports (logo DEPOIS de `load_dotenv(override=True)`)

```python
from news.hook import attach_news, inject_facts, prepare_news
from news.router import router as news_router
```

## 2) Registrar as rotas (logo depois de `app.add_middleware(...)`)

```python
app.include_router(news_router)
```

## 3) Dentro de `chat_completions`, trocar este bloco

```python
    messages = get_messages(req)
    started = time.time()
    errors = []
```

por:

```python
    messages = get_messages(req)

    # --- NOTÍCIAS: só age se a fala pedir notícias; nunca derruba o chat ---
    news = await prepare_news(messages, persona=SYSTEM_PROMPT)
    if news and news.answer:                       # pesquisa com Google Search funcionou
        return attach_news(news.completion(), news)
    if news:                                       # RSS/briefing: fatos vão para o modelo de chat
        messages = inject_facts(messages, news)
    # -----------------------------------------------------------------------

    started = time.time()
    errors = []
```

## 4) Nos dois `return result` (Groq e Gemini) dentro de `chat_completions`

```python
return attach_news(result, news)
```

(São os dois que ficam logo depois dos logs "Resposta recebida do Groq/Gemini em ...".)

## CORS

Se o frontend rodar em outra porta que não a 5173, inclua-a em `allow_origins`.
