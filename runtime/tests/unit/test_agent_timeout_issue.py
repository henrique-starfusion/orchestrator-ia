"""AGENT-TIMEOUT e same_issue sem VAL de entrega vazia."""

from __future__ import annotations

from orchestrator_runtime.tasks.service import TaskService


def test_is_empty_delivery_issue_detects_workspace_kind():
    assert TaskService._is_empty_delivery_issue(
        {"id": "VAL-001", "kind": "workspace_changes", "description": "x"}
    )
    assert TaskService._is_empty_delivery_issue(
        {"id": "VAL-002", "kind": "evidence", "description": "y"}
    )


def test_is_empty_delivery_issue_detects_description_markers():
    assert TaskService._is_empty_delivery_issue(
        {
            "id": "VAL-001",
            "description": "Nenhum entregável no workspace: diff/arquivos vazio",
        }
    )


def test_agent_timeout_not_treated_as_empty_delivery():
    assert not TaskService._is_empty_delivery_issue(
        {
            "id": "AGENT-TIMEOUT",
            "description": "executor timed out",
        }
    )


def test_same_issue_counts_skip_empty_val_on_timeout():
    """Simula a lógica do loop: timeout + VAL vazios não disparam same_issue."""
    issue_counts: dict[str, int] = {}
    agent_timed_out = True
    issues = [
        {
            "id": "AGENT-TIMEOUT",
            "severity": "blocking",
            "description": "timeout",
        },
        {
            "id": "VAL-001",
            "kind": "workspace_changes",
            "severity": "blocking",
            "description": "Critério não atendido: entregável",
        },
        {
            "id": "VAL-002",
            "kind": "evidence",
            "severity": "blocking",
            "description": "Critério não atendido: evidência",
        },
    ]
    for issue in issues:
        iid = issue["id"]
        if agent_timed_out and TaskService._is_empty_delivery_issue(issue):
            continue
        issue_counts[iid] = issue_counts.get(iid, 0) + 1

    assert issue_counts.get("AGENT-TIMEOUT") == 1
    assert "VAL-001" not in issue_counts
    assert "VAL-002" not in issue_counts

    # Segunda iteração com os mesmos VAL vazios ainda não estoura same_issue=2
    for issue in issues:
        iid = issue["id"]
        if agent_timed_out and TaskService._is_empty_delivery_issue(issue):
            continue
        issue_counts[iid] = issue_counts.get(iid, 0) + 1

    assert issue_counts["AGENT-TIMEOUT"] == 2
    assert max(issue_counts.get(k, 0) for k in ("VAL-001", "VAL-002")) == 0
