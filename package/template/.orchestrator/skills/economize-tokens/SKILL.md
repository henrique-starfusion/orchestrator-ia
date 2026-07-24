# Economize Tokens

Orientação para reduzir gasto de tokens sem perder rigor técnico.

## Status

- **Runtime hard:** roteamento por `config/models.json` + `orchestrator route` / MCP
- **Caveman:** **obrigatório** por padrão (`caveman_enabled: true`, intensidade `full`)
- **Always-on tooling:** OpenWolf, Graphify, Superpowers e Caveman injetados nos prompts (0.4.12+)
- Esta skill é orientação; não substitui o runtime

## When to use

- Antes de `orchestrator_run` / `call-agent` / waves multiagente
- Sempre que um agente for invocado pelo runtime (tooling já vem no prompt)

## Rules

1. Ler `.orchestrator/config/models.json` e `config/policies.json`.
2. Caveman full na prosa. Código/paths/erros/JSON/logs/planos/docs: **nunca** abreviar.
3. Classificar tarefa → tier → modelo do CLI alvo (nunca Fable/Opus para docs/trivial).
4. Escopo: citar arquivos; sem dump de repo; sumarizar logs.
5. Preferir MCP/`orchestrator run` a subagentes `Task` no Cursor.
6. OpenWolf (`.wolf/`), Graphify (`.codegraph/` quando existir) e Superpowers (`using-superpowers`) são obrigatórios pelos modelos.

## Outputs

- Escolha de modelo via `orchestrator route --json` ou decisão do Manager no runtime
