"""0.4.47 — circuit breaker de agente (bug-070).

opencode no printbee: binário presente (detect() = disponível) mas o SERVIÇO
morto — 15 agent_runs consecutivas falhando em ~8s com "Unexpected server
error" (validator e executor). Toda rotação de fallback escolhia o mesmo
agente morto e queimava a iteração (agent_performance: 3 runs / 0 sucessos;
12 falhas de validator na frota). Agora N falhas rápidas consecutivas
dentro da janela de 6h colocam o agente em quarentena: os pontos de escolha
de fallback (validator e executor) pulam para o próximo candidato.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.models import OrchestrationPlan
from orchestrator_runtime.tasks.service import TaskService


def _service(project: Path) -> TaskService:
    config = load_config(project, fake_agents=True)
    return TaskService(config, verbose=False)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _fast_fail_run(agent: str, when: datetime) -> dict:
    return {
        "task_id": "t-quarantine",
        "role": "validator",
        "agent": agent,
        "model": "default",
        "command_json": "[]",
        "cwd": ".",
        "started_at": _iso(when),
        "finished_at": _iso(when + timedelta(seconds=8)),
        "exit_code": 1,
        "timed_out": 0,
        "stdout": "",
        "stderr": "Unexpected server error",
        "status": "failed",
        "changed_files_json": "[]",
    }


def _seed_fails(service: TaskService, agent: str, n: int, when: datetime) -> None:
    for i in range(n):
        service.repo.add_agent_run(**_fast_fail_run(agent, when + timedelta(minutes=i)))


NOW = datetime.now(timezone.utc)


def test_tres_falhas_rapidas_quarentenam(project) -> None:
    service = _service(project)
    _seed_fails(service, "opencode", 3, NOW - timedelta(minutes=10))
    assert service._agent_quarantined("opencode") is True


def test_sucesso_recente_quebra_quarentena(project) -> None:
    service = _service(project)
    _seed_fails(service, "opencode", 2, NOW - timedelta(minutes=10))
    ok = _fast_fail_run("opencode", NOW - timedelta(minutes=5))
    ok.update({"status": "completed", "exit_code": 0, "stderr": ""})
    service.repo.add_agent_run(**ok)
    assert service._agent_quarantined("opencode") is False


def test_falha_lenta_nao_e_quarentena(project) -> None:
    service = _service(project)
    for i in range(3):
        run = _fast_fail_run("opencode", NOW - timedelta(minutes=10, seconds=i))
        run["finished_at"] = _iso(NOW - timedelta(minutes=10, seconds=i) + timedelta(seconds=240))
        service.repo.add_agent_run(**run)
    assert service._agent_quarantined("opencode") is False


def test_falhas_fora_da_janela_nao_quarentenam(project) -> None:
    service = _service(project)
    _seed_fails(service, "opencode", 3, NOW - timedelta(hours=7))
    assert service._agent_quarantined("opencode") is False


def test_poucas_runs_nao_quarentenam(project) -> None:
    service = _service(project)
    _seed_fails(service, "opencode", 2, NOW - timedelta(minutes=10))
    assert service._agent_quarantined("opencode") is False


def test_fallback_de_validator_pula_agente_morto(project) -> None:
    service = _service(project)
    service.registry._adapters["opencode"] = FakeAgentAdapter("opencode", project)
    service.registry._adapters["claude"] = FakeAgentAdapter("claude", project)
    _seed_fails(service, "opencode", 3, NOW - timedelta(minutes=10))

    task = service.create_task("task quarantine 0447")
    task.plan = {"fallbacks": {"validator": ["opencode", "claude"]}}
    roles = OrchestrationPlan(
        planner="claude",
        executor="codex",
        validator="gemini",
        fallbacks={"validator": ["opencode", "claude"]},
    )
    escolhido = service._next_validator_fallback(task, roles, current="gemini")
    assert escolhido == "claude", f"quarentenado foi escolhido: {escolhido}"


def test_fallback_sem_quarentena_escolhe_primeiro_disponivel(project) -> None:
    service = _service(project)
    service.registry._adapters["opencode"] = FakeAgentAdapter("opencode", project)
    service.registry._adapters["claude"] = FakeAgentAdapter("claude", project)

    task = service.create_task("task sem quarentena 0447")
    task.plan = {"fallbacks": {"validator": ["opencode", "claude"]}}
    roles = OrchestrationPlan(
        planner="claude",
        executor="codex",
        validator="gemini",
        fallbacks={"validator": ["opencode", "claude"]},
    )
    escolhido = service._next_validator_fallback(task, roles, current="gemini")
    assert escolhido == "opencode"
