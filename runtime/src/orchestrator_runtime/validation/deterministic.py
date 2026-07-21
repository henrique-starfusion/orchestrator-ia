"""Validação determinística, LLM review e completion gate."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator_runtime.tasks.models import AcceptanceCriterion, TaskRecord


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
            ok = self._check_criterion(criterion, changed_files, test_results, project_path)
            criterion.satisfied = ok
            criteria_results.append(
                {"id": criterion.id, "description": criterion.description, "satisfied": ok}
            )
            if criterion.required and not ok:
                issues.append(
                    {
                        "id": next_issue_id(idx),
                        "severity": "blocking",
                        "criterion_id": criterion.id,
                        "description": f"Critério não atendido: {criterion.description}",
                    }
                )
                idx += 1
                score -= 0.2

        failed_tests = [t for t in test_results if t.get("status") not in {"passed", "skipped"}]
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

    def _check_criterion(
        self,
        criterion: AcceptanceCriterion,
        changed_files: list[str],
        test_results: list[dict[str, Any]],
        project_path: Path,
    ) -> bool:
        desc = criterion.description.lower()
        blob = " ".join(changed_files).lower()
        if "soma" in desc:
            core = project_path / "soma" / "core.py"
            if not core.is_file():
                return False
            text = core.read_text(encoding="utf-8")
            if "def soma" not in text:
                return False
        if "teste" in desc or "test" in desc:
            if not any(t.get("status") == "passed" for t in test_results):
                # allow presence of test file for fake early stages
                if not any("test" in f.replace("\\", "/").lower() for f in changed_files):
                    tests_dir = project_path / "tests"
                    if not tests_dir.exists():
                        return False
        if "readme" in desc or "document" in desc or "docs" in desc:
            readme = project_path / "README.md"
            if not readme.is_file():
                return False
            if "soma" in desc or "exemplo" in desc or "uso" in desc:
                if "soma" not in readme.read_text(encoding="utf-8").lower():
                    return False
        if "alterações solicitadas" in desc or "alteracoes solicitadas" in desc:
            return bool(changed_files)
        return True


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
