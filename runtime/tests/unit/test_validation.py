from pathlib import Path

from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    CriterionCheck,
    CriterionKind,
    TaskRecord,
)
from orchestrator_runtime.validation import CompletionGate, DeterministicValidator


def test_validation_and_gate(project):
    task = TaskRecord(
        prompt="soma",
        project_path=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Existe função soma(a, b) retornando a soma numérica",
                kind=CriterionKind.SOMA_MODULE,
                check=CriterionCheck(
                    kind=CriterionKind.SOMA_MODULE,
                    params={"path": "soma/core.py", "symbol": "soma"},
                ),
            )
        ],
    )
    (project / "soma").mkdir()
    (project / "soma" / "core.py").write_text(
        "def soma(a, b):\n    return a + b\n", encoding="utf-8"
    )
    det = DeterministicValidator().evaluate(
        task,
        changed_files=["soma/core.py"],
        test_results=[{"command": "pytest", "status": "passed"}],
        project_path=project,
    )
    assert det["status"] == "approved"
    gate = CompletionGate(0.9)
    ok, _ = gate.can_complete(
        validation=det,
        tests_passed=True,
        documentation_review={"validation": "passed", "required": True},
    )
    assert ok


def test_unknown_criterion_requires_evidence(project):
    task = TaskRecord(
        prompt="x",
        project_path=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Faz algo muito específico sem verificador dedicado",
                kind=CriterionKind.EVIDENCE,
                required=True,
            )
        ],
    )
    det = DeterministicValidator().evaluate(
        task,
        changed_files=[],
        test_results=[],
        project_path=project,
    )
    assert det["status"] == "rejected"
    det_ok = DeterministicValidator().evaluate(
        task,
        changed_files=["src/feature.py"],
        test_results=[],
        project_path=project,
    )
    assert det_ok["status"] == "approved"


def test_legacy_criterion_infers_soma_kind(project):
    """Critérios antigos sem kind ainda validam via inferência."""
    task = TaskRecord(
        prompt="soma",
        project_path=str(project),
        acceptance_criteria=[
            AcceptanceCriterion.model_validate(
                {
                    "id": "AC-001",
                    "description": "Existe função soma(a, b) retornando a soma numérica",
                }
            )
        ],
    )
    assert task.acceptance_criteria[0].kind == CriterionKind.SOMA_MODULE
    (project / "soma").mkdir()
    (project / "soma" / "core.py").write_text(
        "def soma(a, b):\n    return a + b\n", encoding="utf-8"
    )
    det = DeterministicValidator().evaluate(
        task,
        changed_files=["soma/core.py"],
        test_results=[{"command": "pytest", "status": "passed"}],
        project_path=project,
    )
    assert det["status"] == "approved"
    assert det["criteria"][0]["kind"] == "soma_module"
