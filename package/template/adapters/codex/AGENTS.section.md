<!-- orchestrator:call-agent -->
## Calling other agents

To delegate a task to another agent CLI, read `.orchestrator/skills/call-agent/SKILL.md`.
Route the model first (`orchestrator route --task-class <class> --json`), then read the invocation profile in `.orchestrator/agents/profiles/<client>.json`. Shortcut: `orchestrator dispatch`. Never delegate when `ORCHESTRATOR_CHILD_AGENT` is set.
