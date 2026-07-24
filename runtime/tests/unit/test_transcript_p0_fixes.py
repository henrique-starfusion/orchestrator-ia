"""P0s das transcrições PrintBee (2026-07-24): classificação, requires_input,
lock visível, cancel-kill, harness por stack e rotação em timeout sem output."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.agents.process import CliExecutor
from orchestrator_runtime.config import load_config
from orchestrator_runtime.planning.analyzer import TaskAnalyzer
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import (
    TaskState,
    assert_transition,
)
from orchestrator_runtime.testing.discovery import TestDiscovery, stack_test_commands


# ---------------------------------------------------------------- classificação


def test_implementation_verb_overrides_analysis_keyword():
    analyzer = TaskAnalyzer()
    prompt = (
        "Para regras de produção quero selecionar primeiro o metodo de impressão "
        "depois os produtos; use o orquestrador para analisar e fazer estas mudanças"
    )
    assert analyzer.analyze(prompt).task_type == "implementation"


def test_pure_analysis_still_complex_analysis():
    analyzer = TaskAnalyzer()
    prompt = "analise o que o orquestrador executou no projeto e reporte achados"
    assert analyzer.analyze(prompt).task_type == "complex_analysis"


def test_audit_with_recommendations_stays_analysis():
    analyzer = TaskAnalyzer()
    prompt = "auditoria do processo do PrintBee com melhorias recomendadas"
    assert analyzer.analyze(prompt).task_type == "complex_analysis"


def test_implementation_criteria_not_audit_criteria(project):
    """Pedido de implementação não pode receber ACs de auditoria (evidence)."""
    from orchestrator_runtime.planning.analyzer import CriteriaBuilder

    analyzer = TaskAnalyzer()
    prompt = "use o orquestrador para analisar e implementar o multi-select de produtos"
    analysis = analyzer.analyze(prompt)
    criteria = CriteriaBuilder().build(prompt, analysis)
    kinds = {c.kind.value for c in criteria}
    assert "workspace_changes" in kinds


# --------------------------------------------------------------- harness/stack


def test_no_pytest_for_node_project(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    nm = tmp_path / "node_modules" / "some-lib"
    nm.mkdir(parents=True)
    (nm / "test_helper.py").write_text("# vendored", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "app.spec.ts").write_text("it('x', () => {})", encoding="utf-8")

    found = TestDiscovery().discover(tmp_path)
    commands = [" ".join(t.command) for t in found]
    assert commands == ["npm test"]


def test_pytest_kept_for_python_project(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    found = TestDiscovery().discover(tmp_path)
    assert any("pytest" in " ".join(t.command) for t in found)


def test_stack_hint_in_prompts(project):
    (project / "package.json").write_text("{}", encoding="utf-8")
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("qualquer coisa")

    exec_prompt = service._build_executor_prompt(task, {}, [])
    val_prompt = service._build_validator_prompt(task, {}, [], [])
    assert "npm test" in exec_prompt
    assert "npm test" in val_prompt
    assert "REQUIRES_INPUT" in exec_prompt
    assert "perguntas" in exec_prompt
    if os.name == "nt":
        assert "PowerShell" in exec_prompt
    assert stack_test_commands(project) == ["npm test"]


# -------------------------------------------------------------- requires_input


class AskOnceExecutor(FakeAgentAdapter):
    """Executor que pede decisão de negócio em vez de implementar."""

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role not in {"executor", "corrector"}:
            return await super().continue_session(session, request)
        body = {"question": "Opção A ou B para o escopo?", "options": ["A", "B"]}
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="completed",
            exit_code=0,
            stdout=f"REQUIRES_INPUT: {json.dumps(body)}\n",
            stderr="",
            changed_files=[],
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def _service_with(project, adapter_cls):
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = adapter_cls(name, project)
    return service


def test_requires_input_pauses_without_burning_iteration(project):
    service = _service_with(project, AskOnceExecutor)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=3,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.WAITING_FOR_USER
    assert done.iteration == 0, "requires_input não pode consumir iteração"
    assert done.analysis.get("user_question") == "Opção A ou B para o escopo?"
    assert done.analysis.get("user_options") == ["A", "B"]


def test_requires_input_resume_completes_after_answer(project):
    service = _service_with(project, AskOnceExecutor)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=3,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.WAITING_FOR_USER

    # usuário responde; executor passa a implementar (FakeAgentAdapter escreve)
    analysis = dict(done.analysis or {})
    analysis["user_message"] = "Opção A"
    done.analysis = analysis
    service.repo.save(done)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = FakeAgentAdapter(name, project)

    finished = asyncio.run(service.resume(task.id))
    assert finished.status == TaskState.COMPLETED


def test_requires_input_repeat_ends_incomplete(project):
    """Executor que insiste em perguntar não entra em loop infinito."""
    service = _service_with(project, AskOnceExecutor)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=3,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.WAITING_FOR_USER
    finished = asyncio.run(service.resume(task.id))
    assert finished.status == TaskState.INCOMPLETE
    assert "AGENT-REQUIRES-INPUT" in (finished.error or "")


def test_state_machine_allows_requires_input_flow():
    assert_transition(TaskState.EXECUTING, TaskState.WAITING_FOR_USER)
    assert_transition(TaskState.WAITING_FOR_USER, TaskState.ANALYZING)


# ------------------------------------------------------- timeout sem output


class TimeoutNoOutputExecutor(FakeAgentAdapter):
    """Simula Codex/Windows: timeout sem escrever nenhum arquivo."""

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role not in {"executor", "corrector"}:
            return await super().continue_session(session, request)
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="timeout",
            exit_code=-1,
            timed_out=True,
            stdout="reading skills...",
            stderr="",
            changed_files=[],
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def test_timeout_without_output_rotates_and_stops(project):
    service = _service_with(project, TimeoutNoOutputExecutor)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=3,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.INCOMPLETE
    assert "AGENT-TIMEOUT-NO-OUTPUT" in (done.error or "")
    assert done.iteration <= service.config.limits.same_issue_repeat_limit


# ------------------------------------------------------------- lock / cancel


def test_blocked_by_lock_is_visible_in_task_error(project, monkeypatch):
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("hello lock", max_iterations=1)

    def _boom():
        raise TimeoutError("Não foi possível obter lock: fake")

    monkeypatch.setattr(service.lock, "acquire", _boom)
    asyncio.run(service.run_task(task.id))
    refreshed = service.get(task.id)
    assert refreshed.status == TaskState.RECEIVED
    assert (refreshed.error or "").startswith("blocked_by_lock")


def test_blocked_by_lock_error_cleared_on_successful_run(project, monkeypatch):
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = FakeAgentAdapter(name, project)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao"
    )
    task.error = "blocked_by_lock: fake anterior"
    service.repo.save(task)
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.COMPLETED
    assert not (done.error or "").startswith("blocked_by_lock")


def test_cancel_kills_active_child_processes(project, monkeypatch):
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("cancel me", max_iterations=1)

    killed: list[str] = []
    monkeypatch.setattr(
        service.executor, "kill_active", lambda: killed.append("called") or [1234]
    )
    service._running_tasks.add(task.id)
    out = service.cancel(task.id)
    service._running_tasks.discard(task.id)
    assert killed == ["called"]
    assert out.status == TaskState.CANCELLED


def test_cli_executor_tracks_and_kills_active_pids(tmp_path, monkeypatch):
    exe = CliExecutor(tmp_path, echo=False)
    assert exe.kill_active() == []
    exe._active_pids.add(99999901)
    seen: list[int] = []
    monkeypatch.setattr(
        CliExecutor, "_kill_tree", staticmethod(lambda pid: seen.append(pid))
    )
    assert exe.kill_active() == [99999901]
    assert seen == [99999901]


def test_cli_executor_clears_pid_after_run(tmp_path):
    exe = CliExecutor(tmp_path, echo=False)
    result = exe.run(
        ["python", "-c", "print('ok')"],
        cwd=tmp_path,
        timeout_s=60,
        allow_nested=True,
    )
    assert result.exit_code == 0
    assert exe._active_pids == set()


# ------------------------------------------------------------- planner refine


class RecordingAdapter(FakeAgentAdapter):
    timeouts: dict[str, int] = {}

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        RecordingAdapter.timeouts[request.role] = int(request.timeout_s or 0)
        return await super().continue_session(session, request)


def test_planner_refine_capped_at_5_minutes(project):
    RecordingAdapter.timeouts = {}
    service = _service_with(project, RecordingAdapter)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=2,
        timeout=3600,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.COMPLETED
    assert 0 < RecordingAdapter.timeouts.get("planner", 0) <= 300
    # executor mantém o orçamento cheio da role
    assert RecordingAdapter.timeouts.get("executor", 0) > 300
