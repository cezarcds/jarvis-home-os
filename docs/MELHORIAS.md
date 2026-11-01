# Melhorias: o que mudou, o que falta e como testar

## 1. Arquivos alterados (copie por cima dos seus, mesmo caminho)

| Arquivo | O que mudou |
|---|---|
| `frontend/src/index.css` | O núcleo some de verdade durante a cena (antes ficava a 50% de opacidade, por baixo do palco). `--core-opacity: 0.1` deixa um vulto. |
| `frontend/src/App.jsx` | Home sem Eventos/Mídia recente · abrir BRIEFING/ADMIN fecha antes a cena visual · `closeScene` agora cala a voz (`stopSpeaking` não existia) · núcleo 3D é **desmontado** durante a cena (libera a GPU para vídeos) · o quadro negro entra no resumo da cena anterior. |
| `frontend/src/scenes/SceneManager.jsx` | HUD e painel não se misturam mais no fade; HUD coberto sai da composição. |
| `frontend/src/stage/SceneStage.jsx` | Novo layout **`board`** (quadro negro). Nele o mural, o diagrama, as chamadas, as marcas e a palavra-impacto ficam em silêncio. |
| `frontend/src/stage/stage.css` | Estilo do painel `.st-board`. |
| `frontend/src/stage/tuning.js` | `AREAS.board`: posição e tamanho do quadro. |
| `frontend/src/components/ChalkBoard.jsx` | **Novo.** Quadro negro: ícones traçados à mão, setas e rótulos escritos em giz, no ritmo da fala. |
| `backend/scene_schema.py` | Aceita o layout `board` e o bloco `board`; valida (2 a 6 itens, ícones permitidos); só **um** quadro por cena; rebaixa o layout se o bloco faltar; promove um beat se o diretor esquecer de usá-lo. |
| `backend/main.py` | Prompt do diretor ensina o quadro negro · `load_dotenv()` antes dos imports locais · `GEMINI_MODEL` padrão corrigido (`gemini-3.6-flash`). |
| `backend/tests/test_board.py` | Testes do schema (passam). Rode: `cd backend && python tests/test_board.py` |
| `README.md`, `docs/` | README reescrito a partir do código real. |

## 2. Importante: `ParticleWord` foi retirado

Eu tinha criado um `ParticleWord.jsx`, mas o seu palco **já tem** `ImpactWord` (partículas) e `Marks` (traços). O meu era redundante, então não está mais na entrega.
O que você descreveu (palavras voando e interagindo com fotos e vídeos) é ajuste do `ImpactWord.jsx` que existe, e eu ainda não vi esse arquivo.

## 3. Como testar o quadro negro

1. Copie os arquivos, reinicie o backend e recarregue o front.
2. Peça algo de processo: *"Jarvis, como funciona uma usina nuclear?"*, *"por que chove?"*.
3. Em algum momento a tela deve virar um quadro negro que se desenha enquanto o Jarvis fala.
4. Não apareceu? Veja o log do backend: o diretor pode não ter usado `board` (o modelo escolhe). Peça de novo ou diga *"desenhe no quadro..."*. O console do navegador (F12) mostra a cena recebida; procure o campo `board`.

Ajustes rápidos: tamanho/posição em `stage/tuning.js` (`AREAS.board`); ritmo do desenho em `ChalkBoard.jsx` (o desenho termina em 90% da fala; mude `0.9` em `SceneStage.jsx`).

## 4. Ainda não revisado (falta me enviar para eu melhorar partículas e marcas)

`stage/ImpactWord.jsx`, `stage/Marks.jsx`, `stage/Callouts.jsx`, `stage/MediaWall.jsx`, `stage/layouts.js`, `stage/wall.js`, `stage/icons.js`.

Pontos que já aparecem só de ler o que recebi:
- Uma cena comum empilha **seis camadas ao mesmo tempo** (mural, diagrama, título, palavra-impacto, marcas e chamadas). Quando o diretor esquece as chamadas, o schema as **inventa** a partir dos rótulos (`_auto_callouts`), o que aumenta a poluição. Se achar que a tela fica carregada, esse é o primeiro lugar para cortar.
- Em `SceneStage.jsx`, os painéis de vidro (diagrama, gráfico) não têm `z-index` e ficam **abaixo** do mural (`z-index: 2`). Só aparece se os dois se sobrepuserem durante a transição de layout.
- O layout `title` foi desenhado para o título aparecer "sobre o núcleo recuado". Agora que o núcleo some, o título fica sobre o fundo do HUD. Se sentir falta de algo atrás dele, volte `--core-opacity` para `0.1` em `index.css`.

## 5. Limpeza (código morto)

Nada no `App.jsx` importa: `VisualExplain.jsx`, `NewsMural.jsx` (usa classes `.news-card/.news-callout` que não existem), `HeadlinesCard.jsx`, `newsApi.js` (duplica o `api.js`) e o endpoint `/v1/visual-explain` do `main.py`. Confirme antes de apagar:
```bash
grep -rn "NewsMural\|HeadlinesCard\|VisualExplain\|newsApi\|visual-explain" frontend/src backend
```
Faça o mesmo com as cópias soltas na raiz do repositório e com o `LEIA-ME.txt`, depois de compará-las com as versões das pastas.

## 6. Pontos de atenção (não alterei)

- Config e Rotinas, no `NavRail`, abrem a mesma tela (ADMIN).
- CORS só aceita `localhost`/`127.0.0.1`. Se abrir para a rede, lembre que a API controla o computador (`actions/`): não exponha sem autenticação.
- `useSpeech`: `onvoiceschanged` nunca é limpo (vazamento pequeno).
- `api.js › askScene` descarta a mensagem de erro detalhada do backend.

## 7. O que foi validado

- `main.py` e `scene_schema.py`: compilam; 7 cenários de teste do schema passam (quadro usado, esquecido, duplicado, sem bloco, com 1 item, cena antiga, fallback).
- `.jsx`: sintaxe validada com o compilador do TypeScript.
- **Não rodei o HUD no navegador.** Os componentes visuais (`ChalkBoard`, `SceneStage`) precisam de um teste seu.
