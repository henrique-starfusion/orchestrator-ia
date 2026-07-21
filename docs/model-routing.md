# Economia de tokens e roteamento de modelos

O orquestrador escolhe o **modelo certo por tarefa** (`config/models.json`) e pode comprimir prosa com **Caveman opcional**.

Status: roteamento **implementado** · Caveman **opcional/opt-in** · Cursor worker **removido** (use MCP)

## Preferência atual (0.3+)

```bash
orchestrator cursor configure
# no chat: orchestrator_run / orchestrator_delegate

orchestrator route --task-class docs --client claude --json
orchestrator dispatch --task-class docs --client claude --prompt "Atualize o README"
```

`Task model=` no Cursor é **fallback legado**, não o workflow principal.

## Fontes canônicas

| Arquivo | Papel |
|---|---|
| `.orchestrator/config/models.json` | Tiers, task classes, mapa por CLI |
| `.orchestrator/config/routing.json` | Rotas preferidas |
| `.orchestrator/config/policies.json` | Limites + `token_economy` |
| Skill `economize-tokens` | Orientação (não hard runtime) |

## Caveman

Instalado via `orchestrator global-tools` (opt-in).

- Runtime: `caveman_enabled: false` por padrão
- Código, paths e erros: nunca abreviar
- Ativar: pedido explícito do usuário ou policy

## Tiers (capacidade × custo)

| Tier | Uso | Claude (alias) | Cursor (slug, fallback Task) |
|---|---|---|---|
| fast | trivial, classify | `haiku` | `claude-4.5-haiku` |
| balanced | docs, impl, review, tests | `sonnet` | `claude-sonnet-5-thinking-high` |
| deep | architecture, hard debug | `opus` | `claude-opus-4-8-thinking-high` |
| max | complex analysis, long agentic | `fable` | `claude-fable-5-thinking-high` |

Ver também: [`mcp-integration.md`](mcp-integration.md), [`cursor-front-controller.md`](cursor-front-controller.md).
