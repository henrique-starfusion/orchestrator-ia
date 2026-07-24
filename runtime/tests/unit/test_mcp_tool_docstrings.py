"""MCP tool docstrings must advertise auto-dispatch DEFAULT."""

from __future__ import annotations

import inspect

from orchestrator_runtime.mcp import server as mcp_server


def test_orchestrator_run_docstring_declares_default_auto_dispatch() -> None:
    source = inspect.getsource(mcp_server)
    assert "DEFAULT para tarefa não-trivial" in source
    assert "sem o usuário pedir" in source
    assert "Primeira tool de trabalho" in source
    assert "Preferir para plano/review sem escrita" in source
