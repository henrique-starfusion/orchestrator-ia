# Economize Tokens

Cut token spend without losing technical accuracy. Applies caveman communication and cost-aware model routing.

## When to use

- Every orchestration cycle (default on)
- User asks for fewer tokens, brief mode, or caveman
- Before `call-agent` / multi-agent waves

## Rules

1. Read `.orchestrator/config/models.json` and `config/policies.json`.
2. Enable **caveman** (`full` unless user asks lite/ultra). Keep code, paths, errors exact.
3. Classify the task → resolve tier → pick model for the target CLI (never Fable/Opus for docs/trivial).
4. Scope context: cite files/lines; no full-repo dumps; summarize logs.
5. Escalate at most one tier after `validate-result` failure.

## Outputs

- `runtime/results/<task-id>/model-choice.json` with `{ task_class, tier, client, model, caveman }`
