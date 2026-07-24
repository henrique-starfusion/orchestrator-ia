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

## Seleção de skills por modelo leve (0.4.13+)

Antes de chamar modelos pesados (planner/executor/validator), o runtime executa uma **fase de skill selection** com modelo tier `fast` (haiku/gpt-sol):

1. **Discovery**: varre `{project}/.orchestrator/skills`, `.claude/skills`, `.codex/skills`, `.agents/skills` e equivalentes globais do usuário (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`). Apenas skills em disco — nenhum ID fabricado.
2. **Seleção**: envia catálogo ao modelo leve com timeout 120s. Resposta JSON `{"skills":["id1","id2"]}` validada contra o catálogo — IDs inventados são descartados.
3. **Fallback determinístico**: se o CLI falhar, heurística keyword-match seleciona skills cujos id+descrição contêm palavras do prompt.
4. **Injeção**: lista selecionada injetada nos prompts de planner, executor e validator ("use APENAS estas").

Config em `policies.json → skill_selection`:
```json
{
  "enabled": true,
  "model_tier": "fast",
  "max_skills": 5,
  "timeout_s": 120,
  "include_user_global": true
}
```

Role `skill_selector` mapeado para haiku/fast em `models.json → role_model_preferences.skill_selector`.

## Tiers (capacidade × custo)

| Tier | Uso | Claude (alias) | Cursor (slug, fallback Task) |
|---|---|---|---|
| fast | trivial, classify | `haiku` | `claude-4.5-haiku` |
| balanced | docs, impl, review, tests | `sonnet` | `claude-sonnet-5-thinking-high` |
| deep | architecture, hard debug | `opus` | `claude-opus-4-8-thinking-high` |
| max | complex analysis, long agentic | `fable` | `claude-fable-5-thinking-high` |

Ver também: [`mcp-integration.md`](mcp-integration.md), [`cursor-front-controller.md`](cursor-front-controller.md).
