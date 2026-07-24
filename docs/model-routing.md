# Economia de tokens e roteamento de modelos

O orquestrador escolhe o **modelo certo por tarefa** (`config/models.json`) e comprime prosa com **Caveman full** (obrigatório).

Status: roteamento **implementado** · Caveman/OpenWolf/Graphify/Superpowers **always-on (0.4.12+)** · Cursor worker **removido** (use MCP)

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

## Caveman e ferramentas always-on (0.4.12+)

A partir de 0.4.12, quatro ferramentas são **obrigatórias** em todos os prompts do runtime:

| Ferramenta | Quando | Instrução |
|---|---|---|
| **OpenWolf** | Sempre, antes de qualquer ação | Leia `.wolf/STATUS.md`; consulte `.wolf/cerebrum.md` (Do-Not-Repeat); use `.wolf/anatomy.md` |
| **Graphify** | Quando `.codegraph/` existir | Use `codegraph explore` antes de ler arquivos |
| **Superpowers** | Sempre | Invoque `using-superpowers`; aplique skill de processo adequada |
| **Caveman** | Sempre (full) | Prosa concisa; NUNCA abreviar JSON, logs, erros, planos, docs ou código |

- Runtime: `caveman_enabled: true` por padrão (0.4.12+)
- Código, paths, JSON, logs e erros: nunca abreviar (regra mantida)
- Config: `policies.json → token_economy.caveman_enabled` — pode ser sobrescrito por `false` para desabilitar

## Tiers (capacidade × custo)

| Tier | Uso | Claude (alias) | Cursor (slug, fallback Task) |
|---|---|---|---|
| fast | trivial, classify | `haiku` | `claude-4.5-haiku` |
| balanced | docs, impl, review, tests | `sonnet` | `claude-sonnet-5-thinking-high` |
| deep | architecture, hard debug | `opus` | `claude-opus-4-8-thinking-high` |
| max | complex analysis, long agentic | `fable` | `claude-fable-5-thinking-high` |

Ver também: [`mcp-integration.md`](mcp-integration.md), [`cursor-front-controller.md`](cursor-front-controller.md).
