# Economize Tokens

Orientação para reduzir gasto de tokens sem perder rigor técnico.

## Status

- **Runtime hard:** roteamento por `config/models.json` + `orchestrator route` / MCP
- **Caveman:** **opcional** (desabilitado por padrão no runtime/`policies.json`)
- Esta skill é orientação; não substitui o runtime

## When to use

- Antes de `orchestrator_run` / `call-agent` / waves multiagente
- Usuário pede modo breve / caveman explicitamente

## Rules

1. Ler `.orchestrator/config/models.json` e `config/policies.json`.
2. Caveman só se `token_economy.caveman_enabled` ou pedido do usuário. Código/paths/erros nunca abreviar.
3. Classificar tarefa → tier → modelo do CLI alvo (nunca Fable/Opus para docs/trivial).
4. Escopo: citar arquivos; sem dump de repo; sumarizar logs.
5. Preferir MCP/`orchestrator run` a subagentes `Task` no Cursor.

## Outputs

- Escolha de modelo via `orchestrator route --json` ou decisão do Manager no runtime
