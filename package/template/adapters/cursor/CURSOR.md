# Orchestrator adapter for Cursor
#
# Canonical project configuration lives in `.orchestrator/`.

## Token economy + models

- Rules: `.cursor/rules/` + `.orchestrator/config/models.json`.
- Caveman on by default for agent replies (terse, accurate).
- Model picker / Task `model=` by task class:
  - fast → `claude-4.5-haiku`
  - balanced/docs → `claude-sonnet-5-thinking-high`
  - deep → `claude-opus-4-8-thinking-high`
  - max/complex → `claude-fable-5-thinking-high`
  - mechanical edits → `composer-2.5-fast`
