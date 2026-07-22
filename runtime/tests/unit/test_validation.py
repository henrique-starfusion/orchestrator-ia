from pathlib import Path

from orchestrator_runtime.tasks.models import AcceptanceCriterion, TaskRecord
from orchestrator_runtime.validation import CompletionGate, DeterministicValidator


def test_validation_and_gate(project):
    task = TaskRecord(
        prompt="soma",
        project_path=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Existe função soma(a, b) retornando a soma numérica",
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
