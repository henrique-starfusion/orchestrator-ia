"""0.4.40 — bug-056: descoberta de testes cega a stack em subdiretórios.

Auditado na frota (2026-07-28): printbee tem a stack em src/backend (.NET)
e src/frontend (Angular) — raiz sem marcador nenhum e sem repos git filhos.
O bug-048 cobriu repos aninhados (GuardLine), mas projetos com subdirs
comuns seguiam com teste "<none>/skipped" em 100% das tasks: o portão
determinístico nunca tinha evidência de teste. Agora, quando raiz +
extra_dirs não acham nada, o run_all varre subdiretórios até profundidade 2
(pulando node_modules/bin/obj/ocultos e repos filhos com .git).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_descobre_stack_em_subdirs_comuns(tmp_path: Path) -> None:
    from orchestrator_runtime.testing.discovery import TestDiscovery

    backend = tmp_path / "src" / "backend"
    backend.mkdir(parents=True)
    (backend / "app.csproj").write_text("<Project/>\n", encoding="utf-8")
    frontend = tmp_path / "src" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")

    assert TestDiscovery().discover(tmp_path) == []  # raiz limpa
    subs = TestDiscovery().discover_subdirs(tmp_path)
    assert subs == ["src/backend", "src/frontend"]


def test_run_all_cai_no_fallback_de_subdirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestrator_runtime.testing import discovery as disc_mod
    from orchestrator_runtime.testing.discovery import TestRunner

    frontend = tmp_path / "src" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(disc_mod, "which", lambda name: f"/fake/{name}")

    executed: list[tuple[list[str], Path]] = []

    class FakeResult:
        exit_code = 0
        timed_out = False
        stdout = "ok"
        stderr = ""

    class FakeExecutor:
        def run(self, command, cwd=None, timeout_s=None, env=None, allow_nested=False):
            executed.append((list(command), Path(cwd)))
            return FakeResult()

    results = TestRunner(FakeExecutor()).run_all(tmp_path)
    assert executed == [(["npm", "test"], frontend)]
    assert results[0]["status"] == "passed"
    assert results[0]["discovery_source"] == "src/frontend/package.json"


def test_fallback_nao_desce_em_repo_filho_com_git(tmp_path: Path) -> None:
    """Repos git filhos continuam sendo território do bug-048 (extra_dirs)."""
    from orchestrator_runtime.testing.discovery import TestDiscovery

    child = tmp_path / "travelex-api"
    child.mkdir()
    (child / ".git").mkdir()
    (child / "go.mod").write_text("module x\n", encoding="utf-8")

    assert TestDiscovery().discover_subdirs(tmp_path) == []


def test_fallback_pula_ruido_e_ocultos(tmp_path: Path) -> None:
    from orchestrator_runtime.testing.discovery import TestDiscovery

    noise = tmp_path / "node_modules" / "lib"
    noise.mkdir(parents=True)
    (noise / "package.json").write_text("{}\n", encoding="utf-8")
    hidden = tmp_path / ".wolf" / "hooks"
    hidden.mkdir(parents=True)
    (hidden / "package.json").write_text("{}\n", encoding="utf-8")

    assert TestDiscovery().discover_subdirs(tmp_path) == []


def test_raiz_com_stack_nao_dispara_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Se a raiz já tem stack, o fallback não roda (comportamento inalterado)."""
    from orchestrator_runtime.testing import discovery as disc_mod
    from orchestrator_runtime.testing.discovery import TestRunner

    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    sub = tmp_path / "src" / "frontend"
    sub.mkdir(parents=True)
    (sub / "package.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(disc_mod, "which", lambda name: f"/fake/{name}")

    executed: list[list[str]] = []

    class FakeResult:
        exit_code = 0
        timed_out = False
        stdout = "ok"
        stderr = ""

    class FakeExecutor:
        def run(self, command, cwd=None, timeout_s=None, env=None, allow_nested=False):
            executed.append(list(command))
            return FakeResult()

    results = TestRunner(FakeExecutor()).run_all(tmp_path)
    assert executed == [["go", "test", "-short", "./..."]]
    assert all(r["discovery_source"] == "go.mod" for r in results)
