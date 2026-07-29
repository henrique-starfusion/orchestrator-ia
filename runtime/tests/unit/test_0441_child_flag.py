"""bug-057 — ORCHESTRATOR_CHILD_AGENT é valor, não presença.

Agente da GuardLine registrou no Do-Not-Repeat: a var chegava VAZIA (herdada
de shell) e o texto/checagens presence-based faziam o agente principal se
tratar como filho — recusava orquestrar e fazia tudo inline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from orchestrator_runtime.agents.process import CliExecutor, is_child_agent
from orchestrator_runtime.errors import RecursionBlockedError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("0", False),
        (" 0 ", False),
        ("1", True),
        ("true", True),
    ],
)
def test_is_child_agent_por_valor(value, expected, monkeypatch: pytest.MonkeyPatch) -> None:
    if value is None:
        monkeypatch.delenv("ORCHESTRATOR_CHILD_AGENT", raising=False)
    else:
        monkeypatch.setenv("ORCHESTRATOR_CHILD_AGENT", value)
    assert is_child_agent() is expected


def test_executor_bloqueia_somente_filho_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = CliExecutor(project_path=tmp_path)

    monkeypatch.setenv("ORCHESTRATOR_CHILD_AGENT", "1")
    with pytest.raises(RecursionBlockedError):
        executor.run([sys.executable, "-c", "pass"], cwd=tmp_path, timeout_s=60)

    # Vazia herdada não é filho: o processo roda normalmente.
    monkeypatch.setenv("ORCHESTRATOR_CHILD_AGENT", "")
    result = executor.run([sys.executable, "-c", "print('ok')"], cwd=tmp_path, timeout_s=60)
    assert result.exit_code == 0
    assert "ok" in result.stdout
