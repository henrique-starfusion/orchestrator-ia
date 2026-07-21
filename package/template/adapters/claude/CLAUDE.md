# Orchestrator adapter for Claude Code
#
# Canonical project configuration lives in `.orchestrator/`.
# Keep this file minimal and point Claude to the shared orchestrator layout.

Read project rules and skills from `.orchestrator/`.

## Runtime

Prefer the persistent runtime:

```bash
orchestrator run --prompt "<atividade>"
```

MVP roles: Claude plans/validates; Codex executes; runtime runs tests.

## Documentation gate

Ao final de cada tarefa, revisar e atualizar a documentação afetada antes da conclusão.

## Token economy + models

- Follow `.orchestrator/config/models.json` and `config/policies.json`.
- Caveman disabled in runtime artifacts; optional for chat presentation.
- Pick model by task class (aliases):
  - trivial/classify → `haiku`
  - docs/implementation/review → `sonnet`
  - architecture/hard debug → `opus`
  - complex analysis / long agentic → `fable`
- Invoke: `claude --model <alias> ...`. Never use Fable for docs or typos.
