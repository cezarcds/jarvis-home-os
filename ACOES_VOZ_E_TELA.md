# Ações, voz sem clique e visão de tela

O Jarvis agora abre programas, organiza a tela, ouve sem clique e olha a sua tela.
Tudo roda na sua máquina; só a análise da imagem (Gemini) e as respostas de IA usam a internet.

## Como iniciar

Duplo clique em `iniciar_jarvis.bat`. Ele compila o HUD (na primeira vez), instala as dependências,
sobe o backend (`127.0.0.1:8000`) e abre o HUD numa janela de app, sem barra de endereço.

- Rode na sua sessão do Windows (não como serviço): serviços não enxergam a área de trabalho.
- Na primeira vez o Whisper baixa o modelo (`small` ≈ 0,5 GB). O HUD mostra "Carregando o reconhecimento de voz".
- Modo desenvolvimento continua igual: `uvicorn main:app` no backend e `npm run dev` no frontend.
  Com `JARVIS_OPEN_HUD=1` o backend abre a janela de app também nesse modo.
- Depois de mudar o frontend, apague `frontend\dist` para o `.bat` recompilar.

## O que dizer

| Você diz | O que acontece |
|---|---|
| "Jarvis, abre o Profit" / "abre o VS Code" | Abre (ou traz para a frente, se já está aberto) e divide a tela: programa em 2/3, Jarvis em 1/3 |
| "abre o Chrome em tela cheia" | Abre sem organizar |
| "organiza a tela" | Reaplica a divisão na janela em foco |
| "tela cheia" / "me dá a tela toda" | O Jarvis volta a ocupar a tela inteira |
| "Jarvis, olha minha tela" / "o que você acha desse gráfico?" | Captura a janela em foco e analisa |
| "olha o Profit" / "analisa o gráfico do Profit" | Captura a janela do Profit |
| "analisa comigo" / "modo análise" | Cada pergunta seguinte captura a tela de novo (aparece ◉ TELA no cabeçalho) |
| "para de olhar a tela" | Desliga o modo análise e esquece a imagem |

Dizendo só "Jarvis", ele fica 8 s esperando o comando. Depois de falar, ele ouve mais 8 s sem precisar do nome
(para você responder ou perguntar o próximo ponto). Clicar no núcleo continua funcionando como antes.
O botão MIC LIVRE no cabeçalho liga e desliga a escuta.

## Layout

- 1 monitor: programa em 2/3 (à esquerda) e Jarvis em 1/3 (à direita), respeitando a barra de tarefas.
- 2+ monitores: o Jarvis ocupa um monitor inteiro (o primeiro que não é o principal) e o programa vai ao principal.
- Ajustes: `JARVIS_APP_RATIO`, `JARVIS_LAYOUT_MODE` (`auto`/`split`/`dedicated`) e `JARVIS_MONITOR` no `.env`.

## Programas que ele conhece

Padrões: VS Code, Profit, Chrome, Edge, Explorador, Bloco de Notas, Calculadora, Terminal. Qualquer outro programa com
atalho no Menu Iniciar (Spotify, WhatsApp...) também abre pelo nome do atalho.
Para ajustar ou adicionar, crie `~/.jarvis/apps.json` (a mesma entrada com o mesmo `id` substitui a padrão):

```json
[
  {"id": "profit", "nomes": ["profit", "profit pro"], "comandos": ["C:\\Nelogica\\Profit\\profitchart.exe"],
   "titulo_regex": "Profit", "processos": ["profitchart.exe"]},
  {"id": "obs", "nomes": ["obs", "gravador"], "comandos": ["obs64.exe"], "rotulo": "OBS"}
]
```

Para descobrir o `titulo_regex` e o `processos` certos, abra o programa e acesse
`http://localhost:8000/v1/actions/windows` (lista título e executável de cada janela aberta).
O Jarvis só abre o que está no catálogo ou no Menu Iniciar; nunca executa comandos soltos vindos da fala.

## Visão de tela: privacidade

- A imagem é capturada na hora, reduzida, enviada ao Gemini e mantida só em memória (nada vai para o disco).
  Precisa de `GEMINI_API_KEY`; o Groq não enxerga imagem.
- A captura é recusada se houver, na área capturada, uma janela cujo título bate com `JARVIS_BLOCKED_WINDOWS`
  (padrão: bancos e gerenciadores de senha). A checagem considera a janela aberta mesmo que esteja atrás de outra.
- O indicador ◉ TELA fica no cabeçalho enquanto o modo análise está ligado.
- O Whisper não manda áudio para fora: a transcrição é local.
- Números exatos em gráficos (preço, volume) podem ser lidos com erro a partir de imagem. O Jarvis é instruído a avisar
  quando não consegue ler com certeza. Para precisão, o caminho é ligar dados reais do Profit depois.

## Segurança

- O backend sobe só em `127.0.0.1`. O WebSocket de voz recusa origens que não sejam o HUD (um site aberto no navegador
  não consegue usar o seu Jarvis).
- Rotinas salvas continuam só de leitura: ações não entram em rotinas ainda.
- Ações de fora do computador (publicar, enviar, apagar) ainda não existem; quando entrarem, terão confirmação por voz.

## Problemas comuns

- **Não ouve / pede permissão:** libere o microfone na primeira vez (o perfil do HUD é próprio, em `~/.jarvis/hud-profile`).
- **Ele responde a si mesmo:** use fone, ou aumente `UNMUTE_DELAY_MS` em `useHandsFree.js`.
- **Sem som na primeira fala:** clique uma vez na janela do HUD (política de áudio do navegador).
- **"Esse programa roda como administrador":** rode o `iniciar_jarvis.bat` como administrador.
- **Whisper lento:** `JARVIS_WHISPER_MODEL=base` (mais rápido) ou, com placa NVIDIA,
  `JARVIS_WHISPER_DEVICE=cuda` e `JARVIS_WHISPER_COMPUTE=float16`.
- **Errou "Jarvis":** o filtro aceita variações (Garvis, Jarves...). Se ainda falhar, suba o modelo para `medium`.
- **Voz livre indisponível:** `backend\.venv\Scripts\python -m pip install -r backend\requirements-voz.txt`. Se falhar, seu Python provavelmente
  ainda não tem pacote do faster-whisper (acontece com o 3.14): instale o Python 3.12, apague `backend\.venv` e rode o `.bat`.
- **`ImportError` do `pydantic_core` ao iniciar:** o `.venv` versionado no Git veio de outro Python. O `.bat` recria sozinho;
  se preferir à mão, apague `backend\.venv` e rode o `.bat` de novo.

## O que ficou de fora de propósito

Agentes que executam ações (Playwright, UI Automation), o fluxo dos vídeos, o upload no YouTube e o shell desktop
(Electron) são as próximas fases.
