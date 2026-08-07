"""0.4.64 — falta de credencial de agente chega ao CHAT (bug-095).

A 0.4.63 já classificava `auth` e emitia o evento `agent_repair` com o comando de
login. Mas evento mora no `task logs`, e quem precisa agir é o DONO, que está
olhando o chat. Na primeira execução real da 0.4.63 (task b0b9f6cadb7a) o `codex`
caiu por `auth` DUAS vezes e nem o resultado da task nem a saída do `run` disseram
uma palavra — a task terminou COMPLETED e o problema ficou invisível.

Reinstalar não resolve credencial: só a pessoa pode fazer login. Por isso o aviso
tem que sair do runtime e chegar em quem consegue agir.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.config import load_config
from orchestrator_runtime.events import EventType, RuntimeEvent
from orchestrator_runtime.tasks.service import TaskService


def _service(project: Path) -> TaskService:
    return TaskService(load_config(project, fake_agents=True), verbose=False)


def _emit_repair(service: TaskService, task_id: str, **data) -> None:
    event = RuntimeEvent(
        task_id=task_id,
        type=EventType.AGENT_REPAIR,
        role=data.pop("role", "executor"),
        agent=data.pop("agent", "codex"),
        data=data,
    )
    service.repo.add_event(event)


def test_sem_falha_de_auth_nao_inventa_campo(project: Path) -> None:
    service = _service(project)
    task = service.create_task("qualquer coisa")

    assert service.auth_blockers(task.id) == []
    out = service.status(task.id)
    assert "agent_auth_required" not in out
    assert "action_required" not in out


def test_falha_de_auth_aparece_no_status(project: Path) -> None:
    service = _service(project)
    task = service.create_task("qualquer coisa")
    _emit_repair(
        service,
        task.id,
        failure_kind="auth",
        auth_command="codex login",
        agent="codex",
        role="validator",
    )

    out = service.status(task.id)
    assert out["agent_auth_required"] == [
        {"agent": "codex", "role": "validator", "command": "codex login"}
    ]
    assert "codex login" in out["action_required"]
    assert "Reinstalar não resolve" in out["action_required"]


def test_falha_de_install_nao_vira_pedido_ao_dono(project: Path) -> None:
    """Reparo de install o runtime resolve sozinho; não é problema do dono."""
    service = _service(project)
    task = service.create_task("qualquer coisa")
    _emit_repair(
        service, task.id, failure_kind="install", repair_ok=True, agent="opencode"
    )

    assert service.auth_blockers(task.id) == []
    assert "action_required" not in service.status(task.id)


def test_mesmo_agente_em_varios_papeis_aparece_uma_vez(project: Path) -> None:
    """O dono roda o comando de login UMA vez, não uma por papel."""
    service = _service(project)
    task = service.create_task("qualquer coisa")
    for role in ("executor", "validator", "corrector"):
        _emit_repair(
            service,
            task.id,
            failure_kind="auth",
            auth_command="codex login",
            agent="codex",
            role=role,
        )

    blockers = service.auth_blockers(task.id)
    assert len(blockers) == 1
    assert blockers[0]["agent"] == "codex"


def test_agentes_diferentes_aparecem_todos(project: Path) -> None:
    service = _service(project)
    task = service.create_task("qualquer coisa")
    _emit_repair(
        service, task.id, failure_kind="auth", auth_command="codex login", agent="codex"
    )
    _emit_repair(
        service,
        task.id,
        failure_kind="auth",
        auth_command="opencode auth login",
        agent="opencode",
    )

    agentes = sorted(b["agent"] for b in service.auth_blockers(task.id))
    assert agentes == ["codex", "opencode"]
    texto = service.status(task.id)["action_required"]
    assert "codex login" in texto and "opencode auth login" in texto


def test_result_do_mcp_leva_o_pedido_ao_chat(project: Path) -> None:
    """O payload terminal é o que o cliente de chat de fato lê."""
    from orchestrator_runtime.mcp.tools import OrchestratorMcpTools

    service = _service(project)
    task = service.create_task("qualquer coisa")
    _emit_repair(
        service, task.id, failure_kind="auth", auth_command="codex login", agent="codex"
    )

    tools = OrchestratorMcpTools(
        default_workspace=project, fake_agents=True, verbose=False
    )
    out = tools.result({"task_id": task.id})

    assert out["agent_auth_required"][0]["command"] == "codex login"
    assert "codex login" in out["action_required"]
    # remaining_issues era SEMPRE [] — agora carrega o que sobrou de verdade.
    assert any("codex login" in issue for issue in out["remaining_issues"])
    # E em `message`, para cliente que só exibe ela.
    assert "codex login" in out["message"]


def test_result_sem_bloqueio_fica_como_antes(project: Path) -> None:
    from orchestrator_runtime.mcp.tools import OrchestratorMcpTools

    service = _service(project)
    task = service.create_task("qualquer coisa")

    tools = OrchestratorMcpTools(
        default_workspace=project, fake_agents=True, verbose=False
    )
    out = tools.result({"task_id": task.id})

    assert out["remaining_issues"] == []
    assert out["agent_auth_required"] == []
    assert out["action_required"] is None
    assert out["message"].startswith("Tarefa terminal.")
