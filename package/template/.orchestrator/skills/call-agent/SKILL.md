# Call Agent

Invoke a selected agent with scoped context, the **resolved model**, and expected deliverables.

## When to use

- Executing a plan step
- Running read-only analysis in parallel when policy allows

## Preconditions

- Assignment from `select-agents` includes `client`, `model`, `task_class`
- Caveman intensity set (default `full`) unless user disabled

## Invocation (by client)

| Client | Pattern |
|---|---|
| Claude | `claude --model <alias\|id> ...` (aliases: haiku, sonnet, opus, fable) |
| Codex | `codex -m <model> ...` |
| Cursor | select model in IDE / Task `model=` slug from `models.json` |
| Gemini / OpenCode / Kimi | use client map in `config/models.json` when CLI present |

Pass only scoped files and a tight brief. No full-repo paste.

## Outputs

- Agent result in `runtime/results/`
- Logs in `runtime/logs/`
- `model-choice.json` next to the result
