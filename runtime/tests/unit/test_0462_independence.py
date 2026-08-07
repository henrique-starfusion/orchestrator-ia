"""0.4.62 — status diz se houve validação independente (bug-089).

Task 143e8b2ca47b: os DOIS validators saíram exit=1 com zero byte e o
resultado veio COMPLETED score=1.0. A política de não transformar falha de
infra em rejeição de mérito está certa; o silêncio sobre ela, não.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService


def _service(project: Path) -> TaskService:
    return TaskService(load_config(project, fake_agents=True), verbose=False)


def test_sem_rodada_de_validacao_nao_inventa_campo(project: Path) -> None:
    service = _service(project)
    task = service.create_task("qualquer coisa")
    out = service.status(task.id)
    assert "independent_validation" not in out
    assert "validation_warning" not in out


def test_validacao_normal_marca_independente(project: Path) -> None:
    service = _service(project)
    task = service.create_task("qualquer coisa")
    service.repo.add_validation_round(
        task_id=task.id,
        iteration=1,
        status="approved",
        score=1.0,
        payload_json='{"summary":"ok"}',
    )
    out = service.status(task.id)
    assert out["independent_validation"] is True
    assert "validation_warning" not in out


def test_validator_morto_avisa(project: Path) -> None:
    service = _service(project)
    task = service.create_task("qualquer coisa")
    service.repo.add_validation_round(
        task_id=task.id,
        iteration=2,
        status="approved",
        score=1.0,
        payload_json='{"validator_infra_failure": true, "summary":"deterministic"}',
    )
    out = service.status(task.id)
    assert out["independent_validation"] is False
    assert "nenhum validator" in out["validation_warning"]


def test_usa_a_ultima_rodada(project: Path) -> None:
    """Infra caiu na 1a e o fallback respondeu na 2a: vale a última."""
    service = _service(project)
    task = service.create_task("qualquer coisa")
    service.repo.add_validation_round(
        task_id=task.id,
        iteration=1,
        status="approved",
        score=0.9,
        payload_json='{"validator_infra_failure": true}',
    )
    service.repo.add_validation_round(
        task_id=task.id,
        iteration=2,
        status="approved",
        score=1.0,
        payload_json='{"summary":"validator respondeu"}',
    )
    assert service.status(task.id)["independent_validation"] is True
