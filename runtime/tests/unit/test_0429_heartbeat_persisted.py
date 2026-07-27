"""0.4.29 — heartbeat tem que chegar no BANCO, nao so no console.

A 0.4.28 fez o heartbeat do CLI virar evento `agent_progress` para quem observa
por MCP/DB parar de achar que EXECUTING travou. So que o evento ia para o
EventBus — que imprime no stderr e guarda em memoria — e nunca era persistido.

Medido na frota em 2026-07-27, com GuardLine.BR ja na 0.4.28 e uma task VIVA em
EXECUTING: `SELECT COUNT(*) FROM task_events WHERE type='agent_progress'` = 0.
O publico que a correcao existia para atender era exatamente o que nao via nada.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.config import load_config
from orchestrator_runtime.events import EventType
from orchestrator_runtime.tasks.models import TaskRecord
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.service import TaskService


def _heartbeat_events(repo: TaskRepository, task_id: str) -> list[dict]:
    return [
        ev
        for ev in repo.list_events(task_id)
        if ev.get("type") == EventType.AGENT_PROGRESS.value
    ]


def test_heartbeat_vai_para_task_events(project: Path) -> None:
    """Quem le o banco (MCP, Cursor, outra sessao) tem que ver o sinal de vida."""
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = TaskRecord(prompt="x", project_path=str(project))
    service.repo.create(task)

    service._register_heartbeat(task, role="executor", agent_id="claude")
    assert service.executor.on_heartbeat is not None
    service.executor.on_heartbeat(42, 1234)

    events = _heartbeat_events(service.repo, task.id)
    assert len(events) == 1, "heartbeat emitido no bus mas nao persistido (bug-040)"
    data = events[0].get("data") or {}
    assert data["elapsed_s"] == 42
    assert data["pid"] == 1234
    assert events[0]["role"] == "executor"
    assert events[0]["agent"] == "claude"


def test_falha_ao_persistir_nao_derruba_execucao(project: Path) -> None:
    """Sinal de vida e acessorio: se o banco recusar, o agente segue rodando."""
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = TaskRecord(prompt="x", project_path=str(project))
    service.repo.create(task)

    def boom(_event):
        raise RuntimeError("db offline")

    service.repo.add_event = boom  # type: ignore[method-assign]
    service._register_heartbeat(task, role="executor", agent_id="claude")
    service.executor.on_heartbeat(1, 2)  # nao pode levantar


def test_cadencia_vem_do_chamador(project: Path, monkeypatch) -> None:
    """Superficie bloqueante bate mais rapido que quem faz polling."""
    monkeypatch.setenv("ORCHESTRATOR_CALLER", "claude-code")
    blocking = TaskService(load_config(project, fake_agents=True), verbose=False)
    monkeypatch.setenv("ORCHESTRATOR_CALLER", "mcp")
    polling = TaskService(load_config(project, fake_agents=True), verbose=False)

    assert blocking.executor.heartbeat_s < polling.executor.heartbeat_s
