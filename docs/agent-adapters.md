# Agent adapters

Contrato comum: `detect`, `capabilities`, `start`, `continue_session`, `cancel`.

| Agent | Status | Papéis MVP |
|---|---|---|
| claude | implementado | planner, validator |
| codex | implementado | executor, corrector |
| gemini / kimi / opencode | experimental | fallback |
| cursor | ide-client | submissão / aprovação humana — **não worker** |

Profiles: `.orchestrator/agents/profiles/*.json`.

Processo compartilhado: `CliExecutor` (timeout, heartbeat, stream, anti-recursão `ORCHESTRATOR_CHILD_AGENT`).
