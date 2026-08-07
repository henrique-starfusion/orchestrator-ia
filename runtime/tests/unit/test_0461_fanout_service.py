"""0.4.61 — fan-out ponta a ponta: N agentes em worktrees, patches fundidos."""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService

DECOMPOSICAO = json.dumps(
    {
        "subtasks": [
            {
                "id": "s1",
                "title": "API",
                "scope": ["docs/api.md"],
                "instruction": "documentar a API",
            },
            {
                "id": "s2",
                "title": "Deploy",
                "scope": ["docs/deploy.md"],
                "instruction": "documentar o deploy",
            },
        ]
    }
)


class FanoutAdapter(FakeAgentAdapter):
    """Planner devolve a divisão; executor escreve no cwd que recebeu."""

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        now = datetime.now(timezone.utc).isoformat()
        if request.role == "planner" and "subtasks" in request.prompt:
            return AgentResult(
                session_id=session.id,
                agent_id=self.id,
                role=request.role,
                status="completed",
                exit_code=0,
                stdout=DECOMPOSICAO,
                started_at=now,
                finished_at=now,
            )
        if request.role in {"executor", "corrector"}:
            cwd = Path(request.cwd)
            alvo = "docs/api.md" if "docs/api.md" in request.prompt else "docs/deploy.md"
            destino = cwd / alvo
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(f"# {alvo}\nescrito em {cwd.name}\n", encoding="utf-8")
            return AgentResult(
                session_id=session.id,
                agent_id=self.id,
                role=request.role,
                status="completed",
                exit_code=0,
                stdout=f"escrevi {alvo}",
                cwd=str(cwd),
                started_at=now,
                finished_at=now,
            )
        return await super().continue_session(session, request)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True, text=True
    )


@pytest.fixture()
def git_project(project: Path) -> Path:
    """Fixture `project` padrão + repo git com um commit base."""
    _git(project.parent, "init", project.name)
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "test")
    (project / "README.md").write_text("# base\n", encoding="utf-8")
    _git(project, "add", "README.md")
    _git(project, "commit", "-m", "base")
    return project


def _policies(project: Path, **extra) -> None:
    path = project / ".orchestrator" / "config" / "policies.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(extra)
    path.write_text(json.dumps(data), encoding="utf-8")


def _service(project: Path) -> TaskService:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = FanoutAdapter(name, project)
    return service


def test_desligado_por_padrao(git_project: Path) -> None:
    assert _service(git_project)._fanout_enabled() is False


def test_ligado_exige_git(project: Path) -> None:
    """Sem repo git não há worktree — cai no sequencial, sem explodir."""
    _policies(project, allow_parallel_workspace_writes=True)
    assert _service(project)._fanout_enabled() is False


def test_ligado_com_git(git_project: Path) -> None:
    _policies(git_project, allow_parallel_workspace_writes=True)
    assert _service(git_project)._fanout_enabled() is True


def test_max_1_desliga(git_project: Path) -> None:
    _policies(git_project, allow_parallel_workspace_writes=True, max_parallel_subtasks=1)
    assert _service(git_project)._fanout_enabled() is False


def test_fanout_funde_na_arvore_real(git_project: Path) -> None:
    _policies(git_project, allow_parallel_workspace_writes=True)
    service = _service(git_project)
    task = service.create_task("Documentar API e deploy do projeto")

    specs = asyncio.run(service._decompose(task, _roles(service, task)))
    assert [s.id for s in specs] == ["s1", "s2"]

    result = asyncio.run(
        service._run_fanout(task, _roles(service, task), "prompt base", specs)
    )

    assert result.status == "completed"
    assert set(result.changed_files) == {"docs/api.md", "docs/deploy.md"}
    # O que importa: os arquivos existem na árvore REAL, não nos worktrees.
    assert (git_project / "docs" / "api.md").is_file()
    assert (git_project / "docs" / "deploy.md").is_file()


def test_worktrees_sao_limpos(git_project: Path) -> None:
    _policies(git_project, allow_parallel_workspace_writes=True)
    service = _service(git_project)
    task = service.create_task("Documentar API e deploy do projeto")
    specs = asyncio.run(service._decompose(task, _roles(service, task)))
    asyncio.run(service._run_fanout(task, _roles(service, task), "base", specs))

    root = git_project / ".orchestrator" / "runtime" / "worktrees"
    assert not (root / task.id).exists()
    listed = subprocess.run(
        ["git", "worktree", "list"],
        cwd=str(git_project),
        capture_output=True,
        text=True,
        check=True,
    )
    assert task.id not in listed.stdout


def test_subtarefas_ficam_registradas(git_project: Path) -> None:
    _policies(git_project, allow_parallel_workspace_writes=True)
    service = _service(git_project)
    task = service.create_task("Documentar API e deploy do projeto")
    specs = asyncio.run(service._decompose(task, _roles(service, task)))
    asyncio.run(service._run_fanout(task, _roles(service, task), "base", specs))

    rows = service.repo.list_subtasks(task.id)
    assert [r["status"] for r in rows] == ["merged", "merged"]
    assert {r["description"] for r in rows} == {"API", "Deploy"}
    assert rows[0]["payload"]["files"] == ["docs/api.md"]


def test_subtarefa_que_falha_nao_derruba_as_outras(git_project: Path) -> None:
    _policies(git_project, allow_parallel_workspace_writes=True)
    service = _service(git_project)
    task = service.create_task("Documentar API e deploy do projeto")
    specs = asyncio.run(service._decompose(task, _roles(service, task)))

    original = service._run_subtask_blocking

    def _explode(**kwargs):
        if "docs/deploy.md" in kwargs["prompt"]:
            raise RuntimeError("CLI morreu")
        return original(**kwargs)

    service._run_subtask_blocking = _explode  # type: ignore[assignment]
    result = asyncio.run(service._run_fanout(task, _roles(service, task), "base", specs))

    assert result.status == "completed"  # a que sobreviveu entregou
    assert result.changed_files == ["docs/api.md"]
    assert "CLI morreu" in result.stderr
    rows = {r["description"]: r["status"] for r in service.repo.list_subtasks(task.id)}
    assert rows == {"API": "merged", "Deploy": "failed"}


def test_todas_falhando_devolve_failed(git_project: Path) -> None:
    _policies(git_project, allow_parallel_workspace_writes=True)
    service = _service(git_project)
    task = service.create_task("Documentar API e deploy do projeto")
    specs = asyncio.run(service._decompose(task, _roles(service, task)))

    def _explode(**kwargs):
        raise RuntimeError("todos morreram")

    service._run_subtask_blocking = _explode  # type: ignore[assignment]
    result = asyncio.run(service._run_fanout(task, _roles(service, task), "base", specs))

    assert result.status == "failed"
    assert result.changed_files == []


def _roles(service: TaskService, task):
    """Papéis resolvidos como o loop faria."""
    from orchestrator_runtime.tasks.models import OrchestrationPlan

    return OrchestrationPlan(planner="claude", executor="claude", validator="claude")
