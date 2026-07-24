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

## MCP (0.3.0)

Transporte Cursor → Runtime: pacote `orchestrator_runtime.mcp` (`orchestrator-ia`).
Não duplica `TaskService`; apenas expõe tools/resources.

Ver [`mcp-integration.md`](mcp-integration.md).

## Learn-then-compact (0.4.14)

Em cada estado terminal após execução, `TaskService._persist_episode` chama `_learn_then_compact` (choke point único): grava a memória `kind=learning` enriquecida (módulo `memory/learnings.py`) + markdown/index + `.wolf/`, **depois** trunca `runtime/results/{id}/*.txt`. O digest compacto (`session_digest`) vai para `orchestrator_result`/`orchestrator_status`; o cliente IDE retém só digest + `learning_path`. Retrieval em `RETRIEVING_MEMORY` inclui `search_memories(kind="learning")`, injetado nos prompts de planner/executor. Config: `policies.json → context_compaction`.

## Fora do núcleo

OpenWolf, Graphify, Caveman, MCPs globais de terceiros e skills externas são opt-in e **não** são necessários para o runtime.
