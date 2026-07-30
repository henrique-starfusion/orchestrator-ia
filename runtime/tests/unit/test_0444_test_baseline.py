"""0.4.44 — baseline de testes pré-executor (bug-065).

Suite já quebrada na entrada da task (corehub: restore NuGet falho no CLI;
printbee: suite da raiz quebrada — INCOMPLETE 1d63d2a5cb28, citado como
pendência conhecida na 0.4.41) era classificada como failure_kind
"introduced" — bloqueante de mérito — e a task estava condenada a INCOMPLETE
por problema que existia ANTES de o agente tocar qualquer arquivo.

Agora o TestRunner captura uma baseline antes do executor (assinatura =
comando + exit code): falha idêntica na iteração vira "preexisting", que o
determinístico já honra como não-bloqueante. O prompt do corretor informa
sem exigir correção, e o do validador carrega failure_kind com a regra.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from orchestrator_runtime.agents.process import ProcessResult
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState
from orchestrator_runtime.testing.discovery import TestRunner


class _FakeProcExecutor:
    def __init__(self, exit_code: int = 1) -> None:
        self.exit_code = exit_code
        self.calls: list[list[str]] = []

    def run(self, command, *, cwd=None, timeout_s=600, env=None,
            heartbeat_s=None, allow_nested=False, stdin_text=None):
        self.calls.append(list(command))
        return ProcessResult(
            exit_code=self.exit_code,
            stdout="",
            stderr="",
            timed_out=False,
            duration_s=0.01,
            command=list(command),
            cwd=str(cwd or ""),
        )


def _npm_project(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8"
    )
    (tmp_path / "node_modules").mkdir()


def _patch_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "orchestrator_runtime.testing.discovery.which",
        lambda name: f"/fake/{name}",
    )


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int,
         baseline: list[dict] | None) -> list[dict]:
    _npm_project(tmp_path)
    _patch_which(monkeypatch)
    return TestRunner(_FakeProcExecutor(exit_code)).run_all(tmp_path, baseline=baseline)


def test_mesma_assinatura_da_baseline_e_preexisting(tmp_path, monkeypatch) -> None:
    baseline = [{"command": "npm test", "exit_code": 1, "status": "failed"}]
    results = _run(tmp_path, monkeypatch, 1, baseline)
    assert results[0]["failure_kind"] == "preexisting"


def test_exit_code_diferente_da_baseline_e_introduced(tmp_path, monkeypatch) -> None:
    baseline = [{"command": "npm test", "exit_code": 2, "status": "failed"}]
    results = _run(tmp_path, monkeypatch, 1, baseline)
    assert results[0]["failure_kind"] == "introduced"


def test_comando_ausente_da_baseline_e_introduced(tmp_path, monkeypatch) -> None:
    baseline = [{"command": "pytest -q", "exit_code": 1, "status": "failed"}]
    results = _run(tmp_path, monkeypatch, 1, baseline)
    assert results[0]["failure_kind"] == "introduced"


def test_sem_baseline_segue_introduced(tmp_path, monkeypatch) -> None:
    results = _run(tmp_path, monkeypatch, 1, None)
    assert results[0]["failure_kind"] == "introduced"


def test_falha_da_baseline_agora_passando_conta_como_passed(tmp_path, monkeypatch) -> None:
    baseline = [{"command": "npm test", "exit_code": 1, "status": "failed"}]
    results = _run(tmp_path, monkeypatch, 0, baseline)
    assert results[0]["status"] == "passed"
    assert results[0]["failure_kind"] is None


# ------------------------------------------------------------- e2e (service)

def test_suite_pre_quebrada_nao_condena_task(project) -> None:
    """Suite quebrada ANTES da task: failure vira preexisting e a entrega real
    (módulo soma do FakeAgentAdapter) pode COMPLETAR."""
    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_broken.py").write_text(
        "def test_broken_pre():\n    assert False, 'quebra pre-existente'\n",
        encoding="utf-8",
    )
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=2,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.COMPLETED, (
        f"quebra pré-existente condenou a task: status={done.status} "
        f"score={done.last_score} error={done.error}"
    )

    db = project / ".orchestrator" / "data" / "orchestrator.db"
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "select discovery_source, failure_kind, status from test_runs where task_id=?",
        (task.id,),
    ).fetchall()
    conn.close()
    assert any(src.startswith("baseline:") for src, _, _ in rows), rows
    assert any(
        fk == "preexisting" for _, fk, st in rows if st not in {"passed", "skipped"}
    ), rows
