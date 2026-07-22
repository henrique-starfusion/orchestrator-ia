# Orchestrator Runtime

Runtime persistente de orquestração multiagente do `@starfusion/orchestrator`.

## Camada

| Camada | Papel |
|---|---|
| Installer (PowerShell/Node) | Instala `.orchestrator/` |
| **Runtime (este pacote)** | Executa tarefas multiagente |
| Agent adapters | Claude, Codex, Gemini, Kimi, OpenCode |
| Manager model | Rules (default) ou LLM local opcional |

## Requisitos

- Python 3.11+
- Workspace com `.orchestrator/` (via `orchestrator install`)

## Instalação (dev)

```bash
cd runtime
pip install -e ".[dev]"
```

## Uso

Preferencialmente via CLI Node:

```bash
orchestrator run --prompt "Crie um módulo soma com testes e docs"
orchestrator task status <id>
orchestrator task list
```

Direto:

```bash
python -m orchestrator_runtime run --prompt "..."
python -m orchestrator_runtime task list
```

Banco padrão: `<projeto>/.orchestrator/data/orchestrator.db`

## Testes

```bash
cd runtime
pytest
```
