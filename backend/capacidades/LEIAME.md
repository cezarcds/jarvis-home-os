# Capacidades locais (Fase 3)

Três ferramentas, todas nível 1 e **somente dentro de tarefa com contrato aprovado** (o gate recusa
fora disso, e o roteador de voz/LLM nem as enxerga):

| Ferramenta | O que faz | Trava |
|---|---|---|
| `comando.rodar` | roda um comando **nomeado** do catálogo | sem shell; só `nome` e `quantidade` (inteiro validado); pasta = projeto cadastrado, conferida pelo contrato; ambiente mínimo; timeout; mata a árvore de processos; PARAR mata |
| `vscode.abrir_projeto` | abre uma pasta cadastrada no VS Code | caminho completo e idêntico a um projeto cadastrado |
| `navegador.abrir` | abre uma página (Chromium do Playwright) e devolve título e texto | perfil próprio (`~/.jarvis/browser-profile`); `escopo.dominios` do contrato; cada requisição e cada salto de redirecionamento é filtrado; sem downloads; lê dado externo (contamina a execução) |

## Catálogo
`~/.jarvis/comandos.json` (veja `exemplos/comandos.exemplo.json`). Fica fora do Git e é lido a cada uso.
Só você edita: nenhuma ferramenta do Jarvis escreve nele. Arquivo com erro = tudo recusado.

## Navegador
`pip install playwright` e `playwright install chromium` (uma vez). Sem isso a ferramenta aparece como indisponível.
