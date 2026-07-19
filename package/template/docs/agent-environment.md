# Agent Environment

Generic multi-agent environment for software projects.

## Overview

This repository uses `.orchestrator/` as the single canonical source for agent configuration. Individual CLI and IDE agents connect through thin adapters that redirect to that directory.

Supported adapter patterns include Claude Code, Codex CLI, Cursor, Gemini CLI, Kimi CLI, and OpenCode. Additional agents may be registered in `.orchestrator/agents/registry.json`.

## Canonical layout

```text
.orchestrator/
├── VERSION
├── config/          # policies, routing, validation, tools
├── agents/          # registry, capabilities, profiles
├── skills/          # orchestration skills
├── memory/          # durable project knowledge
├── orchestration/   # roles, workflows, templates
├── mcp/             # MCP registry and configs
├── tools/           # tool registry
├── scripts/         # automation
├── hooks/           # lifecycle hooks
├── runtime/         # logs, tasks, plans, results
└── schemas/         # JSON schemas
```

## Operating principles

1. **Single source of truth** — shared settings live only under `.orchestrator/`.
2. **Thin adapters** — agent-specific folders contain redirects, not duplicate config.
3. **Validation before completion** — follow policies in `config/policies.json`.
4. **Incremental upgrades** — compare `VERSION`; add missing pieces without destructive rebuilds.
5. **Shared memory** — persist reusable knowledge under `memory/`.

## Default policies

| Policy | Default |
|--------|---------|
| Maximum iterations | 3 |
| Same issue repeat limit | 2 |
| Minimum validation score | 0.9 |
| Minimum score improvement | 0.03 |
| Independent validation | required |
| Deterministic validation | required |
| Parallel read-only analysis | allowed |
| Parallel workspace writes | disallowed |

## Roles

Defined in `.orchestrator/orchestration/roles.json`:

- **orchestrator** — coordinates work and enforces policies
- **planner** — analyzes and plans tasks
- **executor** — implements changes
- **tester** — runs tests
- **validator** — independently validates results

## Getting started

1. Ensure `.orchestrator/VERSION` exists after bootstrap install.
2. Install the adapter for your agent from the bootstrap template.
3. Run environment validation scripts when available.
4. Use orchestration skills under `.orchestrator/skills/` for standard workflows.

## Documentation scope

Project functional documentation remains in `docs/` at the repository root. This file describes only the agent environment layout and conventions.

---

Copyright StarFusion / Henrique Rodrigues 2026
