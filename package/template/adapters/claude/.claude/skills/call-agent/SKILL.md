---
name: call-agent
description: Invoke another agent CLI (claude/codex/gemini/opencode/kimi) or Cursor Task with the model routed by task_class. Use when delegating work to another agent, dispatching a subtask, or when the user asks to call/consult another CLI agent.
---

# call-agent (stub)

Canonical instructions: read `.orchestrator/skills/call-agent/SKILL.md` and follow it.

Quick reference:
1. `orchestrator route --task-class <class> --client <agent|auto> --json`
2. Read `.orchestrator/agents/profiles/<client>.json` (invocation mechanics).
3. Assemble and run, or shortcut: `orchestrator dispatch --task-class <class> --client <c> --prompt "..."`.

Never delegate if `ORCHESTRATOR_CHILD_AGENT` is set.
