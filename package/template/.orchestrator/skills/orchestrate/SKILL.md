# Orchestrate

Coordinate multi-agent task execution using project policies, **token economy**, and cost-aware model routing.

## When to use

- Starting or resuming an orchestrated task
- Delegating work across agents
- Enforcing iteration and validation limits

## Pipeline

1. `economize-tokens` — caveman + routing rules on
2. `analyze-task` — produce `task_class`
3. `plan-task`
4. `select-agents` — client + model from `config/models.json`
5. `call-agent` — invoke with `--model` / `-m` as mapped
6. `validate-result` → optional one-tier escalate
7. `save-knowledge` when durable

## Inputs

- Task description or plan reference
- `config/policies.json`, `config/models.json`, `config/routing.json`

## Outputs

- Orchestration plan in `runtime/plans/`
- Task state in `runtime/tasks/`
- Per-step `model-choice.json` under `runtime/results/`
