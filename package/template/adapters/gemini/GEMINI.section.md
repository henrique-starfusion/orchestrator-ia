<!-- orchestrator:call-agent -->
## Calling other agents

To delegate a task to another agent CLI, read `.orchestrator/skills/call-agent/SKILL.md` and the profiles in `.orchestrator/agents/profiles/`. Never delegate when `ORCHESTRATOR_CHILD_AGENT` has a non-empty value other than `0` (an empty inherited value does not count).
