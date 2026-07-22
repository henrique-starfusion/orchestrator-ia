# Analyze Task

Break down a user request into goals, constraints, risks, acceptance criteria, and a **task_class** for model routing.

## When to use

- Before planning or agent selection
- When scope is ambiguous

## Required classification

Assign exactly one `task_class` from `config/models.json` (e.g. `docs`, `implementation`, `complex_analysis`).

Hints:

- Documentation / README / comments → `docs` or `documentation` (Sonnet tier)
- Ambiguous multi-system failure / deep research → `complex_analysis` (Fable tier)
- Typos / renames / status → `trivial` (Haiku tier)

## Outputs

- Task analysis artifact in `runtime/tasks/` including `task_class` and suggested `tier`
- Linked memory entries when durable facts emerge
