# Integração: Palavra-impacto + Quadro desenhado

Pacote adaptado do zip `jarvis-impacto-quadro` para o **jarvis-home-os atual** (GitHub `main`).

## Aplicação automática (recomendado)

Na raiz do seu clone:

```bash
# descompacte este zip e rode:
bash adapted/aplicar.sh
# ou, se estiver em outra pasta:
bash caminho/para/adapted/aplicar.sh /caminho/para/jarvis-home-os
```

O script faz os 5 passos:

1. Copia `frontend/src/stage/` (ImpactWord, Marks, handDrawn, icons.js, particles, CSS com fita adesiva…)
2. Substitui `backend/scene_schema.py` + teste
3. Atualiza só o `DIRECTOR_PROMPT` dentro de `backend/main.py` (não sobrescreve o resto)
4. Insere fontes Caveat + Permanent Marker no `index.html`
5. Roda `test-quadro.mjs`, smoke do schema e `pytest test_cena_quadro.py`

## O que entra

### Desenho / quadro
- `handDrawn.js` — traços à mão (círculo, sublinhado, seta, colchete)
- `icons.js` — 35 ícones de traço fino (não confundir com `icons.jsx` dos nós)
- `Marks.jsx` — desenha as marcas no ritmo da fala
- `stage.css` — fita adesiva nos cartões, `mw-tag`, estilos `.mk-*` e `.im-*`
- `tuning.js` — seções `MARKS` e `IMPACT`

### Palavra-impacto
- `ImpactWord.jsx` + `particles.js` — palavra de partículas no centro

### Backend
- `scene_schema.py` — valida `impact`, `marks`, `tag`
- `DIRECTOR_PROMPT` — instrui o LLM a gerar esses campos
- `tests/test_cena_quadro.py`

### Preservado de propósito
- `MediaWall` mantém **NewsFace** / notícias do projeto atual
- `main.py` **não** é substituído por completo — só o prompt do diretor

## Conferência manual

Resposta de `/v1/scene` deve trazer nos beats:

```json
"impact": { "text": "CALOR", "at": 0.4, "tone": "alert" },
"marks": [{ "type": "circle", "target": "reator", "at": 0.3 }]
```

Sem isso na API → prompt/schema não aplicados.  
Com isso e sem desenho na tela → stage/CSS/fontes incompletos.

## Ajustes finos

Em `frontend/src/stage/tuning.js`: `MARKS` e `IMPACT` (tempos, cores, tamanhos).
