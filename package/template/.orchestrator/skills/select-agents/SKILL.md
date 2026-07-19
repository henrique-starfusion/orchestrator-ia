# Select Agents

Choose agents by capability, availability, and **cost-aware** routing.

## When to use

- After a plan exists
- When reassigning failed steps

## Inputs

- `agents/registry.json`, `agents/capabilities.json`
- `config/routing.json`, `config/models.json`, `config/policies.json`
- `agents/detected.json` (which CLIs exist)

## Algorithm

1. Classify step → `task_class` (see `models.json`).
2. Resolve `tier` and preferred `client` from `routing.json` routes.
3. Pick first available client from `prefer_clients` that appears in `detected.json`.
4. Resolve concrete model id/alias from `clients.<cli>.task_map` / `models`.
5. Attach assignment: `{ agent, client, model, task_class, tier, caveman: "full" }`.

## Hard rules

- Docs/documentation → balanced (Claude: `sonnet` / `claude-sonnet-5`), never Fable.
- Complex analysis / long agentic / orchestration plan → max (Claude: `fable`).
- Trivial/classify → fast (Claude: `haiku`).
- Do not assign max-tier models to forbidden task classes in `policies.json`.

## Outputs

- Agent assignment list on the active task (includes model)
