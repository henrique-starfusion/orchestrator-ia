# Call Agent

Invoke a selected agent with scoped context, the **resolved model**, and expected deliverables.

## When to use

- Executing a plan step
- Running read-only analysis in parallel when policy allows

## Preconditions

- Assignment from `select-agents` includes `client`, `model`, `task_class`
- Caveman intensity set (default `full`) unless user disabled

## CRITICAL — Cursor Task

If `client=cursor` (or you are inside Cursor):

1. Run `orchestrator route --task-class <class> --client cursor`
2. Launch `Task` with **`model="<slug>"` exactly** from the route output
3. **Never omit `model=`** — Cursor inherits the parent model (e.g. Grok on every subagent)

## Invocation (by client)

| Client | Pattern |
|---|---|
| Claude | `orchestrator dispatch --task-class <c> --client claude --prompt "..."` or `claude --model <alias>` |
| Codex | `orchestrator dispatch --task-class <c> --client codex --prompt "..."` |
| Cursor | Task tool with mandatory `model=` slug from `route` |
| Gemini / OpenCode / Kimi | map in `config/models.json` when CLI present |

Pass only scoped files and a tight brief. No full-repo paste.

## Outputs

- Agent result in `runtime/results/`
- Logs in `runtime/logs/`
- `*-model-choice.json` from `dispatch` / `route`
