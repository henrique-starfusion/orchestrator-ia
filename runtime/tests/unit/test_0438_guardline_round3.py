"""0.4.38 — terceira rodada GuardLine.BR (bug-051/052/053/054).

bug-051: det reprovava critérios EVIDENCE/CUSTOM sem parâmetros (não
    verificáveis deterministicamente) e o "prefer stricter" vetava aprovação
    1.0 do validador LLM — task ff270e3ff814 iter 1 (entrega já existente de
    run anterior, changed=[] + testes skipped → 4 ACs "não atendidos").
bug-052: same_issue_repeat contava por id posicional (VAL-001 = 1ª issue da
    rodada); problemas diferentes com o mesmo id entre iterações encerravam a
    task por coincidência de posição.
bug-053: validator==executor após rotação de infra virava VAL-IND bloqueante
    em toda iteração — aprovação impossível por causa de infra, não de mérito.
bug-054: `go test ./...` rodava testes live (rede/certs mTLS) que falham
    offline; descoberta Go agora usa `-short` (testing.Short() pula live).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    CriterionCheck,
    CriterionKind,
)
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState


def _ac(kind: CriterionKind, description: str, required: bool = True) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id="AC-001",
        description=description,
        kind=kind,
        check=CriterionCheck(kind=kind, params={}),
        required=required,
    )


# ------------------------------------------------------------------ bug-051

def test_evidence_sem_evidencia_det_nao_reprova(tmp_path: Path) -> None:
    from orchestrator_runtime.validation.deterministic import DeterministicValidator

    class T:
        acceptance_criteria = [_ac(CriterionKind.EVIDENCE, "docs/postman.md atualizado")]

    det = DeterministicValidator().evaluate(
        T(), changed_files=[], test_results=[{"status": "skipped"}], project_path=tmp_path
    )
    assert det["status"] == "approved", det
    assert det["blocking_issues"] == []
    assert det["score"] == 1.0
    crit = det["criteria"][0]
    assert crit["satisfied"] is None
    assert crit["unverifiable"] is True


def test_evidence_com_mudanca_confirma(tmp_path: Path) -> None:
    from orchestrator_runtime.validation.deterministic import DeterministicValidator

    class T:
        acceptance_criteria = [_ac(CriterionKind.EVIDENCE, "docs atualizados")]

    det = DeterministicValidator().evaluate(
        T(), changed_files=["docs/postman.md"], test_results=[], project_path=tmp_path
    )
    assert det["criteria"][0]["satisfied"] is True
    assert det["status"] == "approved"


def test_workspace_changes_ausente_segue_bloqueante(tmp_path: Path) -> None:
    """Regressão: kinds verificáveis continuam reprovando sem evidência."""
    from orchestrator_runtime.validation.deterministic import DeterministicValidator

    class T:
        acceptance_criteria = [_ac(CriterionKind.WORKSPACE_CHANGES, "código alterado")]

    det = DeterministicValidator().evaluate(
        T(), changed_files=[], test_results=[], project_path=tmp_path
    )
    assert det["status"] == "rejected"
    assert det["blocking_issues"], "workspace_changes vazio deve bloquear"


# ------------------------------------------------------------------ bug-052

class RejectDifferentIssuesThenApprove(FakeAgentAdapter):
    """Validator: rejeita 2x com problemas DIFERENTES sob o mesmo id
    posicional (VAL-001), aprova na 3ª. Antes do bug-052, o repeat-limit
    encerrava na 2ª rejeição por coincidência de id."""

    def __init__(self, agent_id: str, project_path: Path) -> None:
        super().__init__(agent_id, project_path)
        self._calls = 0

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role != "validator":
            return await super().continue_session(session, request)
        self._calls += 1
        if self._calls == 1:
            body = {
                "status": "rejected",
                "score": 0.4,
                "blocking_issues": [
                    {"id": "VAL-001", "severity": "blocking",
                     "description": "Critério não atendido: coleção Postman cobre 4 endpoints"}
                ],
            }
        elif self._calls == 2:
            body = {
                "status": "rejected",
                "score": 0.4,
                "blocking_issues": [
                    {"id": "VAL-001", "severity": "blocking",
                     "description": "Teste falhou: go test -short ./..."}
                ],
            }
        else:
            body = {"status": "approved", "score": 0.95, "blocking_issues": []}
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="completed",
            exit_code=0,
            stdout=json.dumps(body),
            stderr="",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def test_issue_diferente_mesmo_id_nao_dispara_repeat_limit(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = RejectDifferentIssuesThenApprove(name, project)

    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=4,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.iteration >= 3, f"repeat-limit por id encerrou cedo: iter={done.iteration}"
    assert done.status == TaskState.COMPLETED


# ------------------------------------------------------------------ bug-053

def test_validator_igual_executor_gira_para_fallback(project, monkeypatch) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)

    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=3,
    )

    from orchestrator_runtime.tasks.models import OrchestrationPlan

    async def fake_select_strategy(t, analysis, **kw):
        return OrchestrationPlan(
            planner="claude",
            executor="codex",
            validator="codex",  # colide com o executor (pós-rotação de infra)
            fallbacks={"validator": ["claude"], "executor": ["claude"]},
        )

    monkeypatch.setattr(service.manager, "select_strategy", fake_select_strategy)
    done = asyncio.run(service.run_task(task.id))
    assert done.status == TaskState.COMPLETED, (
        f"VAL-IND não pode tornar aprovação impossível quando há fallback: "
        f"{done.status} err={done.error}"
    )


# ------------------------------------------------------------------ bug-054

def test_descoberta_go_usa_short(tmp_path: Path) -> None:
    from orchestrator_runtime.testing.discovery import TestDiscovery

    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    found = TestDiscovery().discover(tmp_path)
    go = [t for t in found if t.source == "go.mod"]
    assert go and go[0].command == ["go", "test", "-short", "./..."]
