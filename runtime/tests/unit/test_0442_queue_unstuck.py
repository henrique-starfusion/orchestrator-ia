"""bug-059 — fila presa atrás de task CANCELLED (GuardLine, 29/07).

Coroutine congelada no pré-loop (git pendurado via herança de pipe) mantinha
a task em _running_tasks e o WriteLock preso mesmo após CANCELLED no DB:
toda task nova ficava QUEUED "behind <cancelada>" e o dequeue nunca rodava.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from orchestrator_runtime.execution import git_workspace
from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState


def test_busy_task_id_ignora_zumbi_terminal(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("primeira")
    svc._running_tasks.add(task.id)
    svc.cancel(task.id, reason="cancelada com coroutine zumbi")

    # Task terminal em _running_tasks (coroutine presa) não ocupa o workspace.
    assert svc._busy_task_id(str(project)) is None

    # Task não-terminal em _running_tasks segue ocupando (comportamento normal).
    other = svc.create_task("segunda")
    svc._running_tasks.add(other.id)
    assert svc._busy_task_id(str(project)) == other.id


def test_cancel_dispara_dequeue(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    calls: list[str] = []
    svc._maybe_start_next = calls.append  # type: ignore[method-assign]
    task = svc.create_task("vai ser cancelada")
    svc.cancel(task.id, reason="teste")
    assert calls == [str(project)]


async def test_cancel_no_pre_loop_aborta_e_solta_o_lock(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("cancel chega antes do loop")
    fresh = svc.get(task.id)
    fresh.cancel_requested = True
    svc.repo.save(fresh)

    result = await svc.run_task(task.id)

    assert result.status == TaskState.CANCELLED
    assert not svc.lock.lock_path.exists(), "lock precisa ser liberado"
    assert task.id not in svc._running_tasks
    assert result.iteration == 0, "nenhuma iteração pode ter rodado"


def test_run_git_desliga_fsmonitor_e_usa_arquivo(tmp_path: Path, monkeypatch) -> None:
    captured: dict = {}
    real_popen = subprocess.Popen

    def spy(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["stdout_is_pipe"] = kwargs.get("stdout") == subprocess.PIPE
        return real_popen(cmd, **kwargs)

    monkeypatch.setattr(git_workspace.subprocess, "Popen", spy)
    result = git_workspace._run_git(tmp_path, "--version")

    assert result.returncode == 0
    assert "git version" in result.stdout
    assert "core.fsmonitor=false" in captured["cmd"], "fsmonitor daemon fica de fora"
    assert captured["stdout_is_pipe"] is False, "captura via arquivo, nunca PIPE"
