"""0.4.16 — Testes para fixes PrintBee: lock asyncio, classificação docs, transição
idempotente, TTL RECEIVED, prompt child sem subagentes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from orchestrator_runtime.execution.locks import WriteLock
from orchestrator_runtime.planning.analyzer import TaskAnalyzer
from orchestrator_runtime.tasks.state_machine import TaskState, assert_transition
from orchestrator_runtime.errors import InvalidTransitionError


# ---------------------------------------------------------------------------
# A) WriteLock asyncio single-flight (P0-A)
# ---------------------------------------------------------------------------


async def test_lock_second_asyncio_task_gets_timeout(tmp_path: Path) -> None:
    """Segunda task asyncio recebe TimeoutError imediato — não fica em spinning/deadlock."""
    lock_path = tmp_path / ".orchestrator" / "runtime" / "locks" / "workspace.write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = WriteLock(lock_path, timeout_s=5)

    results: list[str] = []

    async def task1() -> None:
        lock.acquire()
        await asyncio.sleep(0.2)  # yield: task2 pode tentar
        lock.release()
        results.append("t1_done")

    async def task2() -> None:
        await asyncio.sleep(0.05)  # espera task1 adquirir
        try:
            lock.acquire()
            lock.release()
            results.append("t2_acquired")
        except TimeoutError:
            results.append("t2_timeout")

    await asyncio.gather(task1(), task2())
    assert "t1_done" in results
    assert "t2_timeout" in results
    assert "t2_acquired" not in results


async def test_lock_same_asyncio_task_reentrant(tmp_path: Path) -> None:
    """Mesma task asyncio pode adquirir o lock reentrante (depth)."""
    lock_path = tmp_path / ".orchestrator" / "runtime" / "locks" / "workspace.write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = WriteLock(lock_path, timeout_s=5)

    acquired_count = 0

    async def task() -> None:
        nonlocal acquired_count
        lock.acquire()
        acquired_count += 1
        lock.acquire()  # reentrant — mesma task
        acquired_count += 1
        lock.release()
        lock.release()

    await task()
    assert acquired_count == 2


def test_lock_non_async_reentrant(tmp_path: Path) -> None:
    """Contexto não-asyncio (nenhuma task corrente) é reentrante por depth."""
    lock_path = tmp_path / ".orchestrator" / "runtime" / "locks" / "workspace.write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = WriteLock(lock_path, timeout_s=5)

    with patch("orchestrator_runtime.execution.locks.asyncio.current_task", return_value=None):
        lock.acquire()
        lock.acquire()  # deve ser permitido: cur=None, owner=None → None is None True → depth++
        assert lock._depth == 2
        lock.release()
        assert lock._depth == 1
        lock.release()
        assert not lock._held


# ---------------------------------------------------------------------------
# B) Classificação "produção" ≠ docs (P0-B)
# ---------------------------------------------------------------------------


def test_producao_classifica_como_implementation() -> None:
    """Prompt com 'produção' e intent de UI/create não deve virar 'docs'."""
    analyzer = TaskAnalyzer()
    analysis = analyzer.analyze("Regras de Produção create/update checkbox")
    assert analysis.task_type == "implementation", (
        f"Esperado 'implementation', obtido '{analysis.task_type}'"
    )


def test_impl_intent_vence_docs() -> None:
    """Prompt com 'documentação' E verbo de implementação → 'implementation', não 'docs'."""
    analyzer = TaskAnalyzer()
    analysis = analyzer.analyze(
        "Implemente a documentação de onboarding e crie os exemplos"
    )
    assert analysis.task_type == "implementation"


def test_pure_doc_prompt_classifica_docs() -> None:
    """Prompt puramente doc (sem verbo de implementação) ainda é 'docs'."""
    analyzer = TaskAnalyzer()
    analysis = analyzer.analyze("Atualizar README com a seção de changelog")
    assert analysis.task_type == "docs"


def test_documentacao_sem_impl_classifica_docs() -> None:
    """'documentação' sem verbo de implementação continua 'docs'."""
    analyzer = TaskAnalyzer()
    analysis = analyzer.analyze("Revisar documentação do módulo de pagamentos")
    assert analysis.task_type == "docs"


# ---------------------------------------------------------------------------
# C) Transição idempotente same-state (P0-C)
# ---------------------------------------------------------------------------


def test_assert_transition_same_state_noop() -> None:
    """assert_transition com mesmo estado não levanta InvalidTransitionError."""
    # Não deve levantar
    assert_transition(TaskState.RETRIEVING_MEMORY, TaskState.RETRIEVING_MEMORY)
    assert_transition(TaskState.EXECUTING, TaskState.EXECUTING)
    assert_transition(TaskState.COMPLETED, TaskState.COMPLETED)


def test_assert_transition_invalid_still_raises() -> None:
    """Transições inválidas reais ainda levantam InvalidTransitionError."""
    with pytest.raises(InvalidTransitionError):
        assert_transition(TaskState.COMPLETED, TaskState.EXECUTING)


def test_repository_transition_same_state_noop(project: Path) -> None:
    """repo.transition() com same-state retorna task sem salvar evento."""
    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.repository import TaskRepository
    from orchestrator_runtime.tasks.models import TaskRecord

    config = load_config(project)
    repo = TaskRepository(str(config.db_path))
    task = TaskRecord(prompt="test", project_path=str(project))
    repo.create(task)
    # Transiciona para ANALYZING
    task = repo.transition(task, TaskState.ANALYZING, reason="start")
    assert task.status == TaskState.ANALYZING

    events_before = len(repo.list_events(task.id))
    # Same-state: não deve adicionar evento nem levantar
    returned = repo.transition(task, TaskState.ANALYZING, reason="dup")
    assert returned.status == TaskState.ANALYZING
    events_after = len(repo.list_events(task.id))
    assert events_after == events_before, "Same-state não deve emitir evento"


# ---------------------------------------------------------------------------
# D) TTL auto-cancel RECEIVED zumbis (P1-D)
# ---------------------------------------------------------------------------


def test_stale_received_auto_cancelled(project: Path) -> None:
    """Tasks RECEIVED mais antigas que TTL são auto-canceladas em create_task."""
    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.service import TaskService
    from orchestrator_runtime.tasks.repository import TaskRepository
    from orchestrator_runtime.tasks.models import TaskRecord

    config = load_config(project)
    repo = TaskRepository(str(config.db_path))

    # Cria task RECEIVED antiga diretamente no repo
    old_task = TaskRecord(prompt="old task", project_path=str(project))
    repo.create(old_task)

    # Simula task criada há 8h (> default TTL 6h)
    old_created = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()

    def list_tasks_with_old(limit: int = 50) -> list[TaskRecord]:
        tasks = original_list(limit=limit)
        for t in tasks:
            if t.id == old_task.id:
                t.created_at = old_created
        return tasks

    svc = TaskService(config, verbose=False)
    original_list = svc.repo.list_tasks

    with patch.object(svc.repo, "list_tasks", side_effect=list_tasks_with_old):
        cancelled = svc._cancel_stale_received()

    assert cancelled == 1
    refreshed = repo.get(old_task.id)
    assert refreshed is not None
    assert refreshed.status == TaskState.CANCELLED


def test_fresh_received_not_cancelled(project: Path) -> None:
    """Tasks RECEIVED recentes (< TTL) não são canceladas."""
    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.models import TaskRecord
    from orchestrator_runtime.tasks.service import TaskService

    config = load_config(project)
    svc = TaskService(config, verbose=False)

    task = svc.repo.create(TaskRecord(prompt="fresh task", project_path=str(project)))

    cancelled = svc._cancel_stale_received()
    assert cancelled == 0
    refreshed = svc.repo.get(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskState.RECEIVED


def test_config_stale_ttl_from_policies(project: Path) -> None:
    """stale_received_ttl_hours lido de policies.json."""
    import json
    from orchestrator_runtime.config import load_config

    policies_path = project / ".orchestrator" / "config" / "policies.json"
    existing = json.loads(policies_path.read_text())
    existing["stale_received_ttl_hours"] = 12
    policies_path.write_text(json.dumps(existing), encoding="utf-8")

    config = load_config(project)
    assert config.limits.stale_received_ttl_hours == 12


# ---------------------------------------------------------------------------
# E) Bloco ORCHESTRATOR_CHILD_AGENT no prompt (P1-E)
# ---------------------------------------------------------------------------


def test_child_agent_block_always_in_executor_prompt(project: Path) -> None:
    """0.4.18: restrição anti-subagente SEMPRE no prompt do executor.

    CliExecutor seta ORCHESTRATOR_CHILD_AGENT só no filho; o MCP pai não tem
    a env — o bloco precisa ir no prompt sem depender do env do processo pai.
    """
    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.service import TaskService
    from orchestrator_runtime.tasks.models import TaskRecord

    config = load_config(project)
    svc = TaskService(config, verbose=False)
    task = TaskRecord(prompt="test prompt", project_path=str(project))

    prompt = svc._build_executor_prompt(task, {}, [])
    assert "ORCHESTRATOR_CHILD_AGENT" in prompt
    assert "spawn_agent" in prompt
    assert "printbee-patterns" in prompt or "subagentes" in prompt
    # Deve aparecer ANTES do bloco de skills (posição relativa ao título)
    assert prompt.index("ORCHESTRATOR_CHILD_AGENT") < prompt.index("Critérios:")


def test_child_agent_block_in_validator_prompt(project: Path) -> None:
    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.service import TaskService
    from orchestrator_runtime.tasks.models import TaskRecord

    config = load_config(project)
    svc = TaskService(config, verbose=False)
    task = TaskRecord(prompt="test prompt", project_path=str(project))
    prompt = svc._build_validator_prompt(task, {"status": "approved"}, [], [])
    assert "ORCHESTRATOR_CHILD_AGENT" in prompt
    assert "spawn_agent" in prompt
