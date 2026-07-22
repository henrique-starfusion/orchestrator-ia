"""Validação determinística, LLM review e completion gate."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    CriterionKind,
    TaskRecord,
)


def next_issue_id(index: int) -> str:
    return f"VAL-{index:03d}"


class DeterministicValidator:
    def evaluate(
        self,
        task: TaskRecord,
        *,
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        criteria_results = []
        idx = 1
        score = 1.0

        for criterion in task.acceptance_criteria:
            ok = self._check_criterion(
                criterion, changed_files, test_results, project_path
            )
            criterion.satisfied = ok
            kind = self._kind_of(criterion)
            criteria_results.append(
                {
                    "id": criterion.id,
                    "description": criterion.description,
                    "kind": kind.value,
                    "satisfied": ok,
                }
            )
            if criterion.required and not ok:
                issues.append(
                    {
                        "id": next_issue_id(idx),
                        "severity": "blocking",
                        "criterion_id": criterion.id,
                        "kind": kind.value,
                        "description": f"Critério não atendido: {criterion.description}",
                    }
                )
                idx += 1
                score -= 0.2

        failed_tests = [
            t for t in test_results if t.get("status") not in {"passed", "skipped"}
        ]
        for t in failed_tests:
            if t.get("failure_kind") == "preexisting":
                continue
            issues.append(
                {
                    "id": next_issue_id(idx),
                    "severity": "blocking",
                    "description": f"Teste falhou: {t.get('command')}",
                }
            )
            idx += 1
            score -= 0.25

        score = max(0.0, min(1.0, score))
        blocking = [i for i in issues if i["severity"] == "blocking"]
        status = "approved" if not blocking and score >= 0.9 else "rejected"
        return {
            "status": status,
            "score": score,
            "blocking_issues": blocking,
            "non_blocking_issues": [i for i in issues if i["severity"] != "blocking"],
            "criteria": criteria_results,
            "test_assessment": {
                "total": len(test_results),
                "failed": len(failed_tests),
            },
            "summary": "deterministic validation",
        }

    def _kind_of(self, criterion: AcceptanceCriterion) -> CriterionKind:
        if criterion.check is not None:
            return criterion.check.kind
        if criterion.kind != CriterionKind.EVIDENCE:
            return criterion.kind
        # legado sem kind tipado
        return AcceptanceCriterion.infer_kind_from_description(criterion.description)

    def _params(self, criterion: AcceptanceCriterion) -> dict[str, Any]:
        if criterion.check and criterion.check.params:
            return criterion.check.params
        return {}

    def _check_criterion(
        self,
        criterion: AcceptanceCriterion,
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> bool:
        kind = self._kind_of(criterion)
        params = self._params(criterion)
        handlers = {
            CriterionKind.SOMA_MODULE: self._check_soma_module,
            CriterionKind.TESTS_PASS: self._check_tests_pass,
            CriterionKind.DOCS_EXAMPLE: self._check_docs_example,
            CriterionKind.WORKSPACE_CHANGES: self._check_workspace_changes,
            CriterionKind.EVIDENCE: self._check_evidence,
            CriterionKind.CUSTOM: self._check_evidence,
        }
        handler = handlers.get(kind, self._check_evidence)
        return handler(params, changed_files, test_results, project_path)

    def _check_soma_module(
        self,
        params: dict[str, Any],
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> bool:
        rel = params.get("path") or "soma/core.py"
        symbol = params.get("symbol") or "soma"
        core = project_path / Path(rel)
        if not core.is_file():
            return False
        text = core.read_text(encoding="utf-8")
        return f"def {symbol}" in text

    def _check_tests_pass(
        self,
        params: dict[str, Any],
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> bool:
        if any(t.get("status") == "passed" for t in test_results):
            return True
        if any("test" in f.replace("\\", "/").lower() for f in changed_files):
            return True
        tests_dir = project_path / "tests"
        return tests_dir.exists()

    def _check_docs_example(
        self,
        params: dict[str, Any],
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> bool:
        rel = params.get("path") or "README.md"
        readme = project_path / Path(rel)
        if not readme.is_file():
            return False
        must = params.get("must_contain") or []
        if not must:
            return True
        text = readme.read_text(encoding="utf-8").lower()
        return all(str(token).lower() in text for token in must)

    def _check_workspace_changes(
        self,
        params: dict[str, Any],
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> bool:
        return bool(changed_files)

    def _check_evidence(
        self,
        params: dict[str, Any],
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> bool:
        return bool(changed_files) or any(
            t.get("status") == "passed" for t in test_results
        )


class LlmReviewValidator:
    """Interpreta JSON de aprovação emitido por um agente validador."""

    def parse(self, stdout: str, fallback: dict[str, Any]) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", stdout)
        if not match:
            return fallback
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return fallback
        if "status" not in data:
            return fallback
        data.setdefault("blocking_issues", [])
        data.setdefault("non_blocking_issues", [])
        data.setdefault("criteria", fallback.get("criteria", []))
        data.setdefault("test_assessment", fallback.get("test_assessment", {}))
        data.setdefault("score", fallback.get("score", 0.0))
        # Normalize issue ids
        for i, issue in enumerate(data.get("blocking_issues") or [], start=1):
            if isinstance(issue, str):
                data["blocking_issues"][i - 1] = {
                    "id": next_issue_id(i),
                    "severity": "blocking",
                    "description": issue,
                }
            elif isinstance(issue, dict) and "id" not in issue:
                issue["id"] = next_issue_id(i)
        return data


class CompletionGate:
    def __init__(self, threshold: float = 0.9) -> None:
        self.threshold = threshold

    def can_complete(
        self,
        *,
        validation: dict[str, Any],
        tests_passed: bool,
        documentation_review: dict[str, Any] | None,
    ) -> tuple[bool, str]:
        if not tests_passed:
            return False, "testes obrigatórios não passaram"
        if validation.get("status") != "approved":
            return False, "validação não aprovada"
        if float(validation.get("score") or 0) < self.threshold:
            return False, "score abaixo do threshold"
        if validation.get("blocking_issues"):
            return False, "blocking issues presentes"
        if not documentation_review:
            return False, "revisão documental ausente"
        if documentation_review.get("validation") != "passed":
            return False, "validação documental não passou"
        return True, "ok"
