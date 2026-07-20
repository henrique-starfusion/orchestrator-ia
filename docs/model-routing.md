# Economia de tokens e roteamento de modelos

O orquestrador não só delega agentes: ele **escolhe o modelo certo** e **comprime a prosa** (Caveman) para gastar menos tokens com o mesmo rigor técnico.

## Armadilha Cursor (Grok em todos os subagentes)

O `Task` do Cursor, **sem** `model=`, herda o modelo do chat pai. Isso parece orquestrador quebrado, mas e o default do IDE.

```bash
orchestrator route --task-class complex_analysis --client cursor
# Task model="<slug retornado>"

orchestrator dispatch --task-class docs --client claude --prompt "Atualize o README"
```

## Fontes canônicas

| Arquivo | Papel |
|---|---|
| `.orchestrator/config/models.json` | Tiers, task classes, mapa por CLI |
| `.orchestrator/config/routing.json` | Rotas preferidas |
| `.orchestrator/config/policies.json` | Limites + `token_economy` |
| Skill `economize-tokens` | Liga caveman + routing em todo ciclo |

## Caveman (global)

Instalado via `orchestrator global-tools` (`caveman@caveman` + skill `juliusbrussee/caveman`).

- Intensidade padrão: **full** (~75% menos prosa)
- Código, paths e mensagens de erro: nunca abreviar
- Desligar: pedido explícito do usuário (`stop caveman` / normal mode)

## Tiers (capacidade × custo)

| Tier | Uso | Claude (alias) | Cursor (slug) |
|---|---|---|---|
| fast | trivial, classify | `haiku` | `claude-4.5-haiku` |
| balanced | docs, impl, review, tests | `sonnet` | `claude-sonnet-5-thinking-high` |
| deep | architecture, hard debug | `opus` | `claude-opus-4-8-thinking-high` |
| max | complex analysis, long agentic, orchestration plan | `fable` | `claude-fable-5-thinking-high` |

Exemplos alinhados ao pedido do produto:

- Análise complexa → **Fable 5**
- Documentação → **Sonnet 5**
- Typo / status → **Haiku 4.5**

## Por CLI

### Claude Code

```bash
claude --model haiku ...
claude --model sonnet ...
claude --model opus ...
claude --model fable ...
```

Aliases oficiais resolvem para a geração mais nova do tier (`claude-sonnet-5`, `claude-fable-5`, `claude-opus-4-8`, `claude-haiku-4-5`).

### Codex

```bash
codex -m gpt-5.6-terra-medium ...   # fast
codex -m gpt-5.6-sol-medium ...     # balanced
codex -m gpt-5.6-sol ...            # deep/max
```

Evitar `model_reasoning_effort = xhigh` em tarefas fast/balanced.

### Cursor

Usar o picker / `Task model=` com os slugs de `models.json`. Edições mecânicas: `composer-2.5-fast`.

### Gemini / OpenCode / Kimi

Mapa em `models.json`; se o CLI não estiver no PATH, o orquestrador pula sem falhar o bootstrap.

## Escalonamento

1. Escolher o tier mínimo capaz.
2. Se `validate-result` falhar → subir **um** tier (máx. 1 escalada).
3. Nunca usar tier `max` para `docs` / `trivial` (política).

## Atualizar no workspace

```bash
orchestrator update
orchestrator global-tools
```
