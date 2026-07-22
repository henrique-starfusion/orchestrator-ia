# Validate Result

Score deliverables against acceptance criteria using independent and deterministic checks.

## When to use

- After execution or testing
- Before closing an orchestration loop
- Prefer the runtime completion gate (`orchestrator task status`) over manual scoring

## Hard rules

- Never mark COMPLETED because an agent declared success
- Require independent validation when another agent is available
- Require deterministic tests
- **Before completion**: documentation review must exist (`require_documentation_review`)
- Blocking issues use IDs `VAL-001`, `VAL-002`, …

## Inputs

- `config/validation.json`, `config/policies.json`
- Runtime validation rounds in SQLite

## Outputs

- Validation record (runtime DB + optional `runtime/validations/`)
- Documentation review payload before COMPLETED
