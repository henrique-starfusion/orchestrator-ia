# Runtime architecture

Status: **implementado** (MVP 0.2.0)

## Camadas

```text
Installer (Node + PowerShell)
Runtime (Python / orchestrator_runtime)
Agent Adapters (profiles + CliExecutor)
Manager Model (Rules default | LLM opcional)
```

## Persistência

- SQLite: `.orchestrator/data/orchestrator.db`
- Artefatos: `.orchestrator/runtime/results/<task-id>/`
- Export legível: `.orchestrator/memory/episodes/`

## Fluxo

Ver [`task-lifecycle.md`](task-lifecycle.md).

## Pacote

Código em `runtime/src/orchestrator_runtime/`. CLI Node encaminha `run`/`task` via `python -m orchestrator_runtime`.

## Fora do núcleo

OpenWolf, Graphify, Caveman, MCPs e skills externas são opt-in e **não** são necessários para o runtime.
