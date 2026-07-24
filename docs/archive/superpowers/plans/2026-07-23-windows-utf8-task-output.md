# Windows UTF-8 Task Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve PT-BR task text from CLI/MCP ingestion through SQLite and Windows CLI output, while making compact text-list truncation explicit.

**Architecture:** Keep Unicode unchanged in domain/SQLite/MCP layers. Normalize Python runtime standard streams to UTF-8 at the CLI boundary, before Typer or FastMCP writes output. Replace the invisible fixed slice in text task listings with a single-line, word-safe preview ending in an ellipsis; JSON remains lossless.

**Tech Stack:** Python 3.11+, Typer, SQLAlchemy/SQLite, MCP Python SDK, pytest, Node CLI wrapper.

## Global Constraints

- Preserve unrelated dirty-worktree changes.
- Reproduce Windows CP1252 behavior deterministically before production edits.
- Keep MCP stdio stdout protocol-only.
- Bump package/runtime patch version because runtime behavior changes.
- Add migration, changelog, CLI docs, troubleshooting, OpenWolf bug log/status/memory.

---

### Task 1: Deterministic Encoding Regression

**Files:**
- Create: `runtime/tests/unit/test_cli_encoding.py`

**Interfaces:**
- Consumes: `python -m orchestrator_runtime task create|list`, `TaskRepository`, `OrchestratorMcpTools.result`.
- Produces: regression proof that argv ingestion, SQLite, MCP result, JSON output, and text output preserve PT-BR.

- [x] **Step 1: Write the failing subprocess test**

Launch the runtime with `PYTHONUTF8=0` and `PYTHONIOENCODING=cp1252`, create a task containing `correção`, `botões`, `ação`, and `não`, then require UTF-8 bytes from JSON and text list output.

- [x] **Step 2: Run the focused test**

Run: `python -m pytest -q runtime/tests/unit/test_cli_encoding.py`

Expected: FAIL decoding current CP1252 CLI output as UTF-8.

### Task 2: UTF-8 Boundary and Visible Preview

**Files:**
- Modify: `runtime/src/orchestrator_runtime/cli.py`
- Modify: `runtime/tests/unit/test_cli_encoding.py`

**Interfaces:**
- Produces: `_configure_utf8_stdio()` and `_task_preview(prompt, width=72)`.

- [x] **Step 1: Configure stdin/stdout/stderr as UTF-8**

Call guarded `TextIOBase.reconfigure(encoding="utf-8")` at CLI module import so both `python -m orchestrator_runtime` and the installed console script are deterministic on Windows pipes.

- [x] **Step 2: Replace `prompt[:60]`**

Collapse whitespace and use `textwrap.shorten(..., width=72, placeholder="…")`, preserving full content under `task list --json`.

- [x] **Step 3: Run focused and runtime tests**

Run:

```text
python -m pytest -q runtime/tests/unit/test_cli_encoding.py
python -m pytest -q runtime/tests
```

Expected: PASS.

### Task 3: Release and Documentation

**Files:**
- Modify: `VERSION`
- Modify: `.orchestrator/VERSION`
- Modify: `package/template/.orchestrator/VERSION`
- Modify: `package.json`
- Modify: `runtime/pyproject.toml`
- Modify: `runtime/src/orchestrator_runtime/__init__.py`
- Create: `package/migrations/0.4.6-to-0.4.7.ps1`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `docs/orquestrador.md`
- Modify: `docs/installer-architecture.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/troubleshooting.md`
- Modify: `.wolf/buglog.json`
- Modify: `.wolf/STATUS.md`
- Modify: `.wolf/memory.md`
- Modify: `.wolf/cerebrum.md`

**Interfaces:**
- Produces: package/runtime version `0.4.7` and operator guidance.

- [x] **Step 1: Bump all canonical versions and add no-op migration**

Migration records behavior-only upgrade; no workspace data transformation is required.

- [x] **Step 2: Document root cause and output contract**

Document CP1252-vs-UTF-8 symptoms, `task list --text` preview semantics, lossless `--json`, and Cursor reload/update guidance.

- [x] **Step 3: Update OpenWolf handoff records**

Record the byte-level root cause, minimal fix, regression, and next quest.

- [x] **Step 4: Verify release**

Run:

```text
python -m pytest -q runtime/tests
npm test
npm run test:all
openwolf scan --check
git diff --check
```

Expected: all commands exit 0 with no failures.
