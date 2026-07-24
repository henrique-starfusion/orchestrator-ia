from pathlib import Path

from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    CriterionCheck,
    CriterionKind,
    TaskRecord,
)
from orchestrator_runtime.validation import (
    CompletionGate,
    DeterministicValidator,
    LlmReviewValidator,
)


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


FALLBACK = {"status": "rejected", "score": 0.3, "blocking_issues": [], "summary": "det"}


def test_llm_parse_verdict_amid_cli_noise():
    """Log real de CLI: chaves soltas + JSON intermediário + veredito no fim."""
    stdout = (
        "ERROR codex_core::exec: Io(Custom { kind: Other, error: \"x\" })\n"
        '{"status":"validating","score":null,"blocking_issues":[]}\n'
        "mais log { solto\n"
        '{"status":"approved","score":0.95,"blocking_issues":[]}\n'
    )
    out = LlmReviewValidator().parse(stdout, dict(FALLBACK))
    assert out["status"] == "approved"
    assert out["score"] == 0.95


def test_llm_parse_intermediate_status_is_not_verdict():
    """{"status":"validating"} sozinho não é veredito → fallback determinístico."""
    fallback = dict(FALLBACK)
    stdout = '{"status":"validating","score":null,"blocking_issues":[]}\n'
    out = LlmReviewValidator().parse(stdout, fallback)
    assert out is fallback


def test_llm_parse_null_score_uses_fallback_score():
    fallback = dict(FALLBACK)
    stdout = '{"status":"rejected","score":null,"blocking_issues":["faltou doc"]}\n'
    out = LlmReviewValidator().parse(stdout, fallback)
    assert out["status"] == "rejected"
    assert out["score"] == fallback["score"]
    assert out["blocking_issues"][0]["description"] == "faltou doc"


def test_llm_parse_pure_noise_falls_back():
    fallback = dict(FALLBACK)
    out = LlmReviewValidator().parse("Io(Custom { kind: Other })", fallback)
    assert out is fallback
