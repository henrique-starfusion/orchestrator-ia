# QUEUED Orphan Adoption Implementation Plan

> **Execution constraint:** run every step inline in the current child process. Do not delegate, spawn agents, create a daemon, or add a periodic polling thread.

**Goal:** Recover the FIFO head of an abandoned `QUEUED` task through existing poll entry points without stealing work from a live owner or bypassing admission rules.

**Architecture:** Extend the existing orphan-adoption path in `TaskService`. A configurable age threshold makes the FIFO head eligible; a short cross-process `WriteLock` plus the process-local `_adopted` set claims it by refreshing its persisted `updated_at` lease before using the existing `_start_background` path. The candidate still enters through `run_task`, so `_blocking_task_id` remains authoritative for `max_parallel_tasks` and scope overlap.

**Tech Stack:** Python 3.11+, SQLAlchemy/SQLite, pytest through npm scripts, PowerShell package validation.

## Global Constraints

- Keep `orchestrator run` exit-code behavior unchanged.
- Add no daemon, new process, or periodic polling thread.
- Adopt only the first queued task; never scan past a blocked FIFO head.
- Require threshold expiry, dead/terminal blocker or no active task, and normal admission.
- Preserve bug-085 `RECEIVED` adoption.
- Bump patch version from `0.4.77` to `0.4.78` and add the matching migration.

---

### Task 1: Regression proof

**Files:**

- Create: `runtime/tests/unit/test_0478_queued_orphan_adoption.py`
- Reuse: `runtime/tests/unit/test_0460_hang_and_orphan.py`

**Interfaces:**

- Consumes: `TaskService.status`, `TaskService.list_tasks`, `TaskService.follow_events`, `TaskService.create_task`, `_blocking_task_id`, `_start_background`.
- Produces: deterministic coverage for terminal blocker recovery, live-owner protection, FIFO, scope, ceiling, and cross-service idempotence.

- [ ] Create fixtures that set `orphan_queued_adopt_after_s=1`, age `TaskRow.updated_at`, and persist `queued_behind:<id>|pos=N`.
- [ ] Prove a later `status` poll executes the aged FIFO head after its blocker becomes terminal.
- [ ] Prove a live non-terminal blocker prevents adoption even when scopes are disjoint.
- [ ] Prove an overlapping FIFO head prevents adoption of itself and the disjoint task behind it.
- [ ] Prove `max_parallel_tasks` prevents adoption.
- [ ] Prove two service instances polling consecutively start the same task only once.
- [ ] Prove `status`, `list_tasks`, `follow_events`, and `create_task` all reach the adopter.
- [ ] Run the new file before production changes and retain the expected failures as RED evidence.

### Task 2: Common adoption path

**Files:**

- Modify: `runtime/src/orchestrator_runtime/tasks/service.py`
- Modify: `runtime/src/orchestrator_runtime/config.py`
- Modify: `.orchestrator/config/policies.json`
- Modify: `package/template/.orchestrator/config/policies.json`

**Interfaces:**

- Produces: `RuntimeLimits.orphan_queued_adopt_after_s: int` and `TaskService._adopt_orphan_queued(project_path: str) -> bool`.
- Preserves: `_adopt_orphan_received(project_path)` and `_adopt_orphan_received_safe(...)` callers.

- [ ] Add `orphan_queued_adopt_after_s` with default `120` to runtime and both policy files.
- [ ] Add a short `WriteLock` dedicated to queue adoption; use a local thread gate plus `_adopted` for same-process safety.
- [ ] Inspect only `repo.list_queued(project_path)[0]`.
- [ ] Reject recent/cancelled/already-adopted heads.
- [ ] Require the recorded blocker to be terminal, or `_active_tasks` to be empty.
- [ ] Require `_blocking_task_id(project_path, head)` to return `None`.
- [ ] Under the adoption lock, re-read and revalidate the head, then refresh `updated_at` as a durable lease and add its id to `_adopted`.
- [ ] Start through `_start_background(..., name="adopt-queued")`; discard the local claim if thread creation fails so the lease can expire and retry.
- [ ] Call the common safe adopter from `status`, `list_tasks`, `follow_events`, and `create_task`.
- [ ] Keep `run_task`, `_maybe_start_next`, `_drain_queue`, and CLI exit codes unchanged.

### Task 3: Verification and release metadata

**Files:**

- Modify: `CHANGELOG.md`, `docs/configuracao.md`, `docs/fluxo-de-execucao.md`, `docs/troubleshooting.md`
- Modify: `VERSION`, `package/template/.orchestrator/VERSION`, `package.json`, `runtime/pyproject.toml`, `runtime/src/orchestrator_runtime/__init__.py`
- Create: `package/migrations/0.4.77-to-0.4.78.ps1`
- Modify: `.wolf/STATUS.md`, `.wolf/memory.md`, `.wolf/cerebrum.md`, `.wolf/buglog.json`

- [ ] Run focused regression plus bug-085 tests through the runtime npm script.
- [ ] Run the complete runtime suite and `npm test`.
- [ ] Document threshold, eligibility conjunction, FIFO head behavior, poll triggers, lease/idempotence, and absence of a daemon.
- [ ] Bump every canonical version marker to `0.4.78`; add an idempotent migration that inserts the new policy key when absent.
- [ ] Run migration/package checks, review `git diff`, stage only task files, commit, and push `develop`.

## Self-review

- Spec coverage: all eight acceptance conditions map to Tasks 1-3.
- Placeholder scan: no deferred implementation step or business decision remains.
- Type consistency: config key and service helper names are identical across tests, runtime, policy template, docs, and migration.
