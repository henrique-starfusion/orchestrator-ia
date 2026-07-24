from orchestrator_runtime.errors import InvalidTransitionError
from orchestrator_runtime.tasks.state_machine import TaskState, assert_transition, can_resume


def test_valid_transition():
    assert_transition(TaskState.RECEIVED, TaskState.ANALYZING)


def test_invalid_transition():
    try:
        assert_transition(TaskState.RECEIVED, TaskState.VALIDATING)
        assert False, "expected error"
    except InvalidTransitionError:
        pass


def test_delegate_finalization_transitions():
    """Delegate single-role finaliza direto de RECEIVED (anti-órfão)."""
    assert_transition(TaskState.RECEIVED, TaskState.COMPLETED)
    assert_transition(TaskState.RECEIVED, TaskState.INCOMPLETE)
    assert_transition(TaskState.RECEIVED, TaskState.FAILED)


def test_can_resume():
    assert can_resume(TaskState.EXECUTING)
    assert not can_resume(TaskState.COMPLETED)
