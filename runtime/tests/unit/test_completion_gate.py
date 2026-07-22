from orchestrator_runtime.validation import CompletionGate


def test_completion_gate_blocks_without_docs():
    gate = CompletionGate(0.9)
    ok, reason = gate.can_complete(
        validation={"status": "approved", "score": 0.95, "blocking_issues": []},
        tests_passed=True,
        documentation_review=None,
    )
    assert not ok
    assert "document" in reason.lower() or "revis" in reason.lower()
