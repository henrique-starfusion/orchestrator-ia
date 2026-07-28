"""0.4.37 — bug-050: ferramenta ausente não é teste falho.

Medido na task 3b56b92278e9 da GuardLine.BR: o fix do bug-048 passou a
descobrir `go test ./...` e `make test` dentro do repo filho travelex-api,
mas `go` estava fora do PATH do processo e `make` não existe na máquina.
O CliExecutor devolvia exit 127 (WinError 2) e o TestRunner classificava
como status "failed" + failure_kind "introduced" → TEST-FAIL bloqueante →
validador aprovando com 1.0 e a task terminando INCOMPLETE por ambiente,
não por mérito. Agora o run_all faz pre-flight which() e reporta
status "skipped" + failure_kind "tool_missing".
"""

from __future__ import annotations

from pathlib import Path

import pytest


class _FakeResult:
    exit_code = 0
    timed_out = False
    stdout = "ok"
    stderr = ""


def _go_module(root: Path, name: str = "travelex-api") -> Path:
    child = root / name
    child.mkdir(parents=True, exist_ok=True)
    (child / "go.mod").write_text("module travelex\n", encoding="utf-8")
    return child


def test_ferramenta_ausente_vira_skipped_tool_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestrator_runtime.testing import discovery as disc_mod
    from orchestrator_runtime.testing.discovery import TestRunner

    root = tmp_path / "mono"
    root.mkdir()
    child = _go_module(root)
    (child / "Makefile").write_text("test:\n\tgo test ./...\n", encoding="utf-8")

    # Nem `go` nem `make` no PATH.
    monkeypatch.setattr(disc_mod, "which", lambda name: None)

    class FakeExecutor:
        def run(self, *a, **k):  # pragma: no cover - não deve ser chamado
            raise AssertionError("não pode executar comando sem ferramenta")

    results = TestRunner(FakeExecutor()).run_all(root, extra_dirs=["travelex-api"])
    assert len(results) == 2
    assert {r["command"] for r in results} == {"go test ./...", "make test"}
    for r in results:
        assert r["status"] == "skipped"
        assert r["failure_kind"] == "tool_missing"
        assert r["exit_code"] is None
        assert "ausente no PATH" in r["stderr"]
    # Nada de "failed": o portão tests_passed (passed|skipped) não bloqueia.
    assert all(r["status"] in {"passed", "skipped"} for r in results)


def test_ferramenta_presente_executa_normal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestrator_runtime.testing import discovery as disc_mod
    from orchestrator_runtime.testing.discovery import TestRunner

    root = tmp_path / "mono"
    root.mkdir()
    _go_module(root)
    monkeypatch.setattr(disc_mod, "which", lambda name: f"/fake/{name}")

    executed: list[list[str]] = []

    class FakeExecutor:
        def run(self, command, cwd=None, timeout_s=None, env=None, allow_nested=False):
            executed.append(list(command))
            return _FakeResult()

    results = TestRunner(FakeExecutor()).run_all(root, extra_dirs=["travelex-api"])
    assert executed == [["go", "test", "./..."]]
    assert results[0]["status"] == "passed"
    assert results[0]["failure_kind"] is None


def test_misto_ausente_e_presente_só_roda_o_possível(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestrator_runtime.testing import discovery as disc_mod
    from orchestrator_runtime.testing.discovery import TestRunner

    root = tmp_path / "mono"
    root.mkdir()
    child = _go_module(root)
    # Marca também stack Python no filho: pytest "existe", go não.
    (child / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

    present = {"pytest", "python"}
    monkeypatch.setattr(
        disc_mod, "which", lambda name: f"/fake/{name}" if name in present else None
    )

    executed: list[list[str]] = []

    class FakeExecutor:
        def run(self, command, cwd=None, timeout_s=None, env=None, allow_nested=False):
            executed.append(list(command))
            return _FakeResult()

    results = TestRunner(FakeExecutor()).run_all(root, extra_dirs=["travelex-api"])
    by_cmd = {r["command"]: r for r in results}
    assert by_cmd["go test ./..."]["status"] == "skipped"
    assert by_cmd["go test ./..."]["failure_kind"] == "tool_missing"
    assert by_cmd["pytest -q"]["status"] == "passed"
    assert executed == [["pytest", "-q"]]


def test_falha_real_de_teste_continua_bloqueante(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regressão: suite que roda e FALHA (exit != 0) segue status failed."""
    from orchestrator_runtime.testing import discovery as disc_mod
    from orchestrator_runtime.testing.discovery import TestRunner

    root = tmp_path / "mono"
    root.mkdir()
    _go_module(root)
    monkeypatch.setattr(disc_mod, "which", lambda name: f"/fake/{name}")

    class FailingResult:
        exit_code = 1
        timed_out = False
        stdout = "FAIL: TestSoma"
        stderr = ""

    class FakeExecutor:
        def run(self, command, cwd=None, timeout_s=None, env=None, allow_nested=False):
            return FailingResult()

    results = TestRunner(FakeExecutor()).run_all(root, extra_dirs=["travelex-api"])
    assert results[0]["status"] == "failed"
    assert results[0]["failure_kind"] == "introduced"
