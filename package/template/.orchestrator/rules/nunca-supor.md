---
description: Verificar suposicao evidencia medir consultar antes de afirmar sobre codigo banco comando ferramenta API externa versao ou licenca
alwaysApply: false
---

# Nunca supor: verificar, medir ou consultar

Afirmação técnica exige evidência verificável. Antes de afirmar:

- abra o arquivo e leia o trecho relevante;
- rode o comando e examine a saída;
- consulte o banco quando a resposta estiver nos dados;
- leia o `--help` da ferramenta antes de declarar capacidade ou limitação.

Prefira número a adjetivo. `92,6% dos eventos são heartbeat` informa mais que
`muitos eventos são heartbeat`.

Cite a evidência junto da afirmação: `arquivo:linha` para conteúdo versionado ou
a saída relevante do comando executado. Não separe conclusão e prova.

Informação fora da máquina — licença de terceiro, API externa, versão de
ferramenta — deve ser consultada na fonte oficial na internet. Não responda de
memória: o modelo tem corte de conhecimento.

Se não sabe e não pode verificar, diga que não sabe. Não preencha a lacuna com
uma explicação apenas plausível.

## Casos medidos em 2026-08-11

- Suposição: `orchestrator_message` conversa com task viva. Evidência:
  `runtime/src/orchestrator_runtime/mcp/tools.py:932` exige
  `WAITING_FOR_USER` e reinicia a análise.
- Suposição: injetar mensagem em agente rodando é impossível. Evidência: saída
  de `claude --help` contém `--input-format stream-json` para entrada streaming
  em tempo real. A limitação estava no adapter, não no CLI.
- Suposição: `same_issue_repeat_limit` é contador global. Evidência:
  `runtime/src/orchestrator_runtime/tasks/service.py:2964` mostra contagem por
  critério.
- Suposição: a história Git foi destruída. Evidência: `.git/shallow` havia sido
  criado pelo `fetch --depth 1` do próprio sync; a causa virou bug-117.
