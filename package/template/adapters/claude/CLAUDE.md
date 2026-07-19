# Orchestrator adapter for Claude Code
#
# Canonical project configuration lives in `.orchestrator/`.
# Keep this file minimal and point Claude to the shared orchestrator layout.

Read project rules and skills from `.orchestrator/`.

## Token economy + models

- Follow `.orchestrator/config/models.json` and `config/policies.json`.
- Default communication: **caveman** (`full`) — terse, no fluff; code/errors exact.
- Pick model by task class (aliases):
  - trivial/classify → `haiku` (`claude-haiku-4-5`)
  - docs/implementation/review → `sonnet` (`claude-sonnet-5`)
  - architecture/hard debug → `opus` (`claude-opus-4-8`)
  - complex analysis / long agentic / orchestration plan → `fable` (`claude-fable-5`)
- Invoke: `claude --model <alias> ...`. Never use Fable for docs or typos.
