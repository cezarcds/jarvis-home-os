# Conectores de escrita (Fase 4)

| Ferramenta | Nível | Onde roda | Trava (no código) |
|---|---|---|---|
| `youtube.upload_privado` | 2 | só em tarefa com contrato | sem parâmetro de visibilidade; corpo sempre `private`; retorno da API conferido; formato/tamanho/título/tags validados; `arquivo` dentro de `escopo.pastas`, `conta` em `escopo.contas`; limite diário no contrato |
| `gmail.rascunhar` | 2 | tarefa ou conversa (confirma por clique fora de contrato) | só chama `drafts.create` (teste confere que não existe chamada de envio) |
| `gmail.enviar` | 3 | **só por clique, nunca em tarefa** (o gate recusa mesmo listada no contrato) | texto inteiro na confirmação (corpo até 1500 caracteres); destinatários validados, sem quebra de linha em cabeçalho |
| `analytics.consultar` | 0 | qualquer | métricas/dimensões só de uma lista permitida (ou `customEvent:`/`customUser:`), janela e linhas limitadas; marca a sessão como contaminada |

## Autorizar (opcional, só o que for usar)
Dentro de `backend/`: `python -m routines.google_auth --youtube --gmail`.
Sem o escopo, a ferramenta aparece como indisponível e diz o comando. `gmail.compose` permite rascunho **e** envio (o Google não separa);
quem separa é o Jarvis.

## Limites conhecidos
- `conta` é o rótulo do contrato; o canal real é o do token do Google.
- Upload com erro de servidor/rede no meio vira item "incerto": a tarefa pausa até você conferir no YouTube e liberar.
- A documentação atual do YouTube diz que projetos não verificados não são mais forçados a privado: a garantia é do Jarvis.
- Cota de envio vigente: confirme no Google Cloud (a página de `videos.insert` cita 100 chamadas/dia no balde de uploads).
