"""0.4.43 — P0 spawn/discovery/dispatch (bug-061/062/063/064).

bug-061: cmd.exe processa .CMD/.BAT com teto de 8191 chars por linha — muito
    abaixo dos 32767 do CreateProcess que o ARGV_LIMIT (30000) assumia. Prompt
    de 9635 chars para codex.CMD morria no spawn ("Linha de comando muito
    longa.", exit 1) ANTES de o agente iniciar; executor E corrector zerados
    na task b6c4e9ba0a15 do corehub. Reproduzido na maquina: 8100 passa,
    8200 falha. Teto efetivo agora depende do executavel resolvido.
bug-062: .NET 10 preview (10.0.400) recusa `dotnet test` sem argumento mesmo
    com UM .sln na pasta quando ha .csproj em subdirs (MSB1011, reproduzido
    no corehub). Discovery passa o alvo explicito (.sln > .slnx > .csproj).
bug-063: discovery do bug-056 passou a achar testes nao-executaveis:
    `npm test` sem node_modules ("'stencil' nao e reconhecido", cobrado como
    merito) e `ng test` em modo watch (Karma) travado 601s ate timeout, 2x
    por task = 20min queimados. Sem node_modules -> skipped/deps_missing;
    `ng test` sem --watch ganha `-- --watch=false`.
bug-064: double-submit (2 creates em 16s via MCP) gerava tasks gêmeas; uma
    travava RECEIVED sem dono porque _cancel_stale_received so rodava no
    create_task. create_task ficou idempotente (janela 120s) e status/list
    tambem varrem RECEIVED velhas.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentRequest, AgentSession
from orchestrator_runtime.agents.base_adapters import (
    ARGV_LIMIT,
    CMD_ARGV_LIMIT,
    ProfileCliAdapter,
    _effective_argv_limit,
)
from orchestrator_runtime.agents.process import ProcessResult
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState
from orchestrator_runtime.testing.discovery import TestDiscovery, TestRunner


class _RecordingExecutor:
    """CliExecutor fake: registra comando/stdin e devolve sucesso."""

    def __init__(self, exit_code: int = 0) -> None:
        self.calls: list[dict] = []
        self.exit_code = exit_code

    def run(self, command, *, cwd=None, timeout_s=600, env=None,
            heartbeat_s=None, allow_nested=False, stdin_text=None):
        self.calls.append({"command": list(command), "stdin_text": stdin_text})
        return ProcessResult(
            exit_code=self.exit_code,
            stdout="ok",
            stderr="",
            timed_out=False,
            duration_s=0.01,
            command=list(command),
            cwd=str(cwd or ""),
        )


def _adapter(profile: dict, executor: _RecordingExecutor) -> ProfileCliAdapter:
    return ProfileCliAdapter(profile, executor)


def _run_session(adapter: ProfileCliAdapter, request: AgentRequest):
    session = AgentSession(agent_id=adapter.id, role=request.role)
    return asyncio.run(adapter.continue_session(session, request))


# ------------------------------------------------------------------ bug-061

def test_limite_efetivo_cmd_vs_nativo() -> None:
    assert _effective_argv_limit([r"C:\npm\codex.CMD", "exec"]) == CMD_ARGV_LIMIT
    assert _effective_argv_limit(["gemini.bat", "-p"]) == CMD_ARGV_LIMIT
    assert _effective_argv_limit([r"C:\bin\claude.exe", "-p"]) == ARGV_LIMIT
    assert _effective_argv_limit(["claude", "-p"]) == ARGV_LIMIT
    assert CMD_ARGV_LIMIT < 8191  # teto real do cmd.exe, com margem


def test_prompt_grande_para_cmd_vai_por_stdin(tmp_path: Path, monkeypatch) -> None:
    profile = {
        "id": "codex",
        "kind": "cli",
        "invoke": {"subcommand": ["exec"], "prompt_via": "arg", "prompt_flag": None},
        "timeout_default_s": 60,
    }
    monkeypatch.setattr(
        "orchestrator_runtime.agents.base_adapters.which",
        lambda name: r"C:\npm\codex.CMD",
    )
    exe = _RecordingExecutor()
    adapter = _adapter(profile, exe)
    prompt = "x" * 9000  # > 8191 do cmd.exe, < 32767 do CreateProcess
    request = AgentRequest(role="executor", prompt=prompt, cwd=str(tmp_path))
    result = _run_session(adapter, request)

    assert result.status == "completed"
    assert exe.calls[0]["stdin_text"] == prompt
    assert all(len(a) < 9000 for a in exe.calls[0]["command"])


def test_prompt_grande_para_exe_nativo_segue_no_argv(tmp_path: Path, monkeypatch) -> None:
    profile = {
        "id": "claude",
        "kind": "cli",
        "invoke": {"prompt_flag": "-p", "prompt_via": "arg"},
        "timeout_default_s": 60,
    }
    monkeypatch.setattr(
        "orchestrator_runtime.agents.base_adapters.which",
        lambda name: r"C:\bin\claude.exe",
    )
    exe = _RecordingExecutor()
    adapter = _adapter(profile, exe)
    prompt = "y" * 9000  # cabe nos 32767 do CreateProcess
    request = AgentRequest(role="executor", prompt=prompt, cwd=str(tmp_path))
    result = _run_session(adapter, request)

    assert result.status == "completed"
    assert exe.calls[0]["stdin_text"] is None
    assert prompt in exe.calls[0]["command"]


def test_sem_stdin_e_overflow_falha_com_diagnostico(tmp_path: Path, monkeypatch) -> None:
    profile = {
        "id": "kimi",
        "kind": "cli",
        "invoke": {"prompt_flag": "-p", "prompt_via": "arg", "prompt_stdin": False},
        "timeout_default_s": 60,
    }
    monkeypatch.setattr(
        "orchestrator_runtime.agents.base_adapters.which",
        lambda name: r"C:\npm\kimi.CMD",
    )
    exe = _RecordingExecutor()
    adapter = _adapter(profile, exe)
    request = AgentRequest(role="executor", prompt="z" * 9000, cwd=str(tmp_path))
    result = _run_session(adapter, request)

    assert result.status == "failed"
    assert result.exit_code == 126
    assert "[argv-overflow]" in result.stderr
    assert exe.calls == []  # nem tentou spawnar para morrer no cmd.exe


# ------------------------------------------------------------------ bug-062

def test_dotnet_alvo_explicito_sln(tmp_path: Path) -> None:
    (tmp_path / "CoreHub.sln").write_text("", encoding="utf-8")
    sub = tmp_path / "API"
    sub.mkdir()
    (sub / "CoreHub.API.csproj").write_text("", encoding="utf-8")
    found = TestDiscovery().discover(tmp_path)
    assert ["dotnet", "test", "CoreHub.sln"] in [t.command for t in found]


def test_dotnet_alvo_slnx(tmp_path: Path) -> None:
    (tmp_path / "App.slnx").write_text("", encoding="utf-8")
    found = TestDiscovery().discover(tmp_path)
    assert ["dotnet", "test", "App.slnx"] in [t.command for t in found]


def test_dotnet_alvo_csproj_sem_sln(tmp_path: Path) -> None:
    (tmp_path / "Lib.csproj").write_text("", encoding="utf-8")
    found = TestDiscovery().discover(tmp_path)
    assert ["dotnet", "test", "Lib.csproj"] in [t.command for t in found]


def test_subdir_marker_reconhece_slnx(tmp_path: Path) -> None:
    sub = tmp_path / "backend"
    sub.mkdir()
    (sub / "App.slnx").write_text("", encoding="utf-8")
    assert "backend" in TestDiscovery().discover_subdirs(tmp_path)


# ------------------------------------------------------------------ bug-063

def _patch_which_npm(monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator_runtime.testing.discovery.which",
        lambda name: f"/usr/bin/{name}",
    )


def test_npm_sem_node_modules_skip_deps_missing(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "stencil test --spec"}}', encoding="utf-8"
    )
    _patch_which_npm(monkeypatch)
    exe = _RecordingExecutor()
    results = TestRunner(exe).run_all(tmp_path)
    assert results[0]["status"] == "skipped"
    assert results[0]["failure_kind"] == "deps_missing"
    assert exe.calls == []


def test_ng_test_ganha_watch_false(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "ng test"}}', encoding="utf-8"
    )
    _patch_which_npm(monkeypatch)
    exe = _RecordingExecutor()
    TestRunner(exe).run_all(tmp_path)
    assert exe.calls[0]["command"] == ["npm", "test", "--", "--watch=false"]


def test_jest_nao_ganha_watch_flag(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "jest"}}', encoding="utf-8"
    )
    _patch_which_npm(monkeypatch)
    exe = _RecordingExecutor()
    TestRunner(exe).run_all(tmp_path)
    assert exe.calls[0]["command"] == ["npm", "test"]


def test_ng_test_com_watch_no_script_nao_duplica(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "ng test --watch=false --browsers=ChromeHeadless"}}',
        encoding="utf-8",
    )
    _patch_which_npm(monkeypatch)
    exe = _RecordingExecutor()
    TestRunner(exe).run_all(tmp_path)
    assert exe.calls[0]["command"] == ["npm", "test"]


# ------------------------------------------------------------------ bug-064

def test_create_task_dedup_double_submit(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    t1 = service.create_task("mesmo prompt dedup 0443")
    t2 = service.create_task("mesmo prompt dedup 0443")
    assert t2.id == t1.id  # double-submit devolve a existente
    t3 = service.create_task("prompt diferente 0443")
    assert t3.id != t1.id
    t4 = service.create_task("mesmo prompt dedup 0443", dry_run=True)
    assert t4.id != t1.id  # dry_run diferente = intencao diferente


def test_status_varre_received_zumbi(project, monkeypatch) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("vai virar zumbi 0443")
    assert task.status == TaskState.RECEIVED

    real_datetime = datetime

    class _Future:
        @staticmethod
        def now(tz=None):
            return real_datetime.now(timezone.utc) + timedelta(hours=7)

        fromisoformat = staticmethod(real_datetime.fromisoformat)

    monkeypatch.setattr("orchestrator_runtime.tasks.service.datetime", _Future)
    out = service.status(task.id)
    assert out["status"] == "CANCELLED"  # TTL default 6h excedido no poll


def test_list_tasks_varre_received_zumbi(project, monkeypatch) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("zumbi via list 0443")

    real_datetime = datetime

    class _Future:
        @staticmethod
        def now(tz=None):
            return real_datetime.now(timezone.utc) + timedelta(hours=7)

        fromisoformat = staticmethod(real_datetime.fromisoformat)

    monkeypatch.setattr("orchestrator_runtime.tasks.service.datetime", _Future)
    tasks = {t.id: t for t in service.list_tasks()}
    assert tasks[task.id].status == TaskState.CANCELLED
