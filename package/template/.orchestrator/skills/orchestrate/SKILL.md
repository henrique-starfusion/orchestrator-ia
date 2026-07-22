# Orchestrate

Coordinate multi-agent task execution using the **persistent runtime** (preferred) or skills as guidance.

## Preferred path (hard runtime)

```bash
orchestrator run --prompt "<atividade>"
orchestrator task status <id>
```

The runtime executes: analyze → memory → plan → select agents → execute → test → validate → correct → documentation → consolidate.

## When to use skills

- Explaining policy to an IDE agent
- Manual steps when runtime Python is unavailable

## Pipeline (skills / soft)

1. Prefer `orchestrator run` over manual Task delegation
2. `analyze-task` — produce `task_class` if needed for `route`/`dispatch`
3. `plan-task` / `select-agents` / `call-agent` only as fallback
4. `validate-result` — never accept self-declared success
5. **Documentation gate**: before completion, review and update affected docs
6. `save-knowledge` when durable

## Hard rules

- Cursor is an IDE **client**, not a worker (do not select as planner/executor/validator)
- Validation must be independent when another agent is available
- Deterministic tests are run by the runtime
- No task completes without documentation review record
- Caveman disabled in runtime/logs/JSON until stabilization

## Inputs

- Task description
- `config/policies.json`, `config/models.json`, `config/manager_model.json`

## Outputs

- SQLite: `.orchestrator/data/orchestrator.db`
- Events/artifacts under `.orchestrator/runtime/`
- Human-readable episodes under `.orchestrator/memory/episodes/`
