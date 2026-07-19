# Orchestrator Environment

Canonical source for multi-agent configuration in this project.

## Purpose

The `.orchestrator/` directory is the single source of truth for:

- orchestrator configuration and policies
- agent registry, capabilities, and profiles
- skills and workflows
- shared memory and knowledge
- MCP and tool registries
- validation, hooks, scripts, and runtime artifacts

Individual AI agents (Claude Code, Codex, Cursor, Gemini, Kimi, OpenCode, and others) must not maintain divergent copies of this configuration. Each agent uses a thin adapter that points here.

## Layout

| Path | Role |
|------|------|
| `config/` | Core settings, policies, routing, validation, tools |
| `agents/` | Registry, detection, capabilities, profiles, adapters |
| `skills/` | Reusable orchestration skills |
| `memory/` | Project knowledge, decisions, episodes, lessons |
| `orchestration/` | Roles, workflows, templates, schemas |
| `mcp/` | MCP server registry and configs |
| `tools/` | Tool registry and integrations |
| `scripts/` | Automation scripts |
| `hooks/` | Lifecycle hooks (active, tested, disabled) |
| `runtime/` | Logs, tasks, plans, results, validations |
| `schemas/` | JSON schemas for orchestrator artifacts |

## Version

See `VERSION` in this directory. Upgrade incrementally; do not rebuild from scratch when versions match.

---

Copyright StarFusion / Henrique Rodrigues 2026
