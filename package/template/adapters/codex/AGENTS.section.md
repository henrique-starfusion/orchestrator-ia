<!-- orchestrator:call-agent -->
## Calling other agents

Prefer the persistent runtime: `orchestrator run --prompt "..."`.
For single-shot CLI: read `.orchestrator/skills/call-agent/SKILL.md`, then `orchestrator route` / `orchestrator dispatch`.
Never select Cursor as worker. Never delegate when `ORCHESTRATOR_CHILD_AGENT` is set.
Ao final de cada tarefa, revisar e atualizar a documentação afetada antes da conclusão.
