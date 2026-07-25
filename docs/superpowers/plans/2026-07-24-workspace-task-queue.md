# Workspace Task Queue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Impedir 2 execuções simultâneas no mesmo workspace; enfileirar e dequeue automático.

**Architecture:** Estado `QUEUED` + detecção de busy no `run_task` + `_dequeue_next` no `finally` após liberar WriteLock. MCP/status expõem posição e `blocked_by`.

**Tech Stack:** Python asyncio, SQLite TaskRepository, pytest.

---

### Task 1: Estado QUEUED + transições

**Files:**
- Modify: `runtime/src/orchestrator_runtime/tasks/state_machine.py`
- Test: `runtime/tests/unit/test_workspace_queue.py`

Steps: add `QUEUED`; `RECEIVED→QUEUED`, `QUEUED→ANALYZING|RECEIVED|CANCELLED|FAILED`; update `can_resume`/TERMINAL as needed (QUEUED is resumable).

### Task 2: Repo list queued + active

**Files:**
- Modify: `runtime/src/orchestrator_runtime/tasks/repository.py`
- Methods: `list_queued(project_path)`, `find_active_task(project_path)` (status not RECEIVED/QUEUED/terminal)

### Task 3: run_task enqueue + dequeue

**Files:**
- Modify: `runtime/src/orchestrator_runtime/tasks/service.py`
- On TimeoutError / busy: transition QUEUED instead of silent blocked_by_lock
- After lock release: `_maybe_start_next(project_path)`
- `status()` includes queue_position / blocked_by

### Task 4: MCP surface

**Files:**
- Modify: `runtime/src/orchestrator_runtime/mcp/tools.py` (run return + status)

### Task 5: Docs + version 0.4.19

CHANGELOG, troubleshooting, migration, VERSION files, diagnostics feature flag.
