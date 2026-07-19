# Orchestrator adapter for Codex CLI
#
# Canonical project configuration lives in `.orchestrator/`.

Use `.orchestrator/` as the shared source for rules, skills, memory, and orchestration.

## Token economy + models

- Follow `.orchestrator/config/models.json`.
- Prefer caveman-style terse replies (skill/plugin when available).
- Model via `codex -m <model>`:
  - fast → `gpt-5.6-terra-medium`
  - balanced (docs/impl) → `gpt-5.6-sol-medium`
  - deep/max → `gpt-5.6-sol`
- Do not leave reasoning at `xhigh` for trivial/docs tasks.
