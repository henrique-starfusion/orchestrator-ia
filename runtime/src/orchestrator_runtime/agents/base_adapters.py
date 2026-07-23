"""Adaptador CLI genérico baseado em profile JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator_runtime.agents.base import (
    AgentAdapter,
    AgentCapabilities,
    AgentRequest,
    AgentResult,
    AgentSession,
    AgentStatus,
)
from orchestrator_runtime.agents.process import CliExecutor, which
from orchestrator_runtime.errors import AgentUnavailableError


class ProfileCliAdapter(AgentAdapter):
    def __init__(
        self,
        profile: dict[str, Any],
        executor: CliExecutor,
        *,
        experimental: bool = False,
        capabilities: AgentCapabilities | None = None,
    ) -> None:
        self.id = str(profile.get("id"))
        self.kind = str(profile.get("kind", "cli"))
        self.profile = profile
        self.executor = executor
        self.experimental = experimental
        self._capabilities = capabilities or AgentCapabilities(
            roles=["planner", "executor", "validator"],
            can_write=True,
            can_validate=True,
            experimental=experimental,
            executable=self.kind == "cli",
        )

    def detect(self) -> AgentStatus:
        path = which(self.id)
        return AgentStatus(
            id=self.id,
            available=bool(path) and self.kind == "cli",
            path=path,
            kind=self.kind,
            verified=bool(self.profile.get("verified", False)),
            notes=str(self.profile.get("notes", "")),
        )

    def capabilities(self) -> AgentCapabilities:
        return self._capabilities

    def build_command(self, request: AgentRequest) -> list[str]:
        invoke = self.profile.get("invoke") or {}
        args: list[str] = [self.id]
        for part in invoke.get("subcommand") or []:
            args.append(str(part))
        # Flags de sandbox/automação do profile (ex.: codex --full-auto)
        for part in invoke.get("sandbox_flags") or []:
            args.append(str(part))
        if request.model and request.model_flag:
            args.extend([request.model_flag, request.model])
        elif request.model and self.profile.get("model_flag"):
            args.extend([str(self.profile["model_flag"]), request.model])
        prompt_flag = invoke.get("prompt_flag", None)
        # JSON null -> None; missing key defaults to -p for safety only if documented
        if "prompt_flag" in invoke:
            prompt_flag = invoke.get("prompt_flag")
        if prompt_flag:
            args.extend([str(prompt_flag), request.prompt])
        else:
            args.append(request.prompt)
        args.extend(request.extra_args)
        return args

    async def start(self, request: AgentRequest) -> AgentSession:
        status = self.detect()
        if not status.available:
            raise AgentUnavailableError(f"Agente indisponivel: {self.id}")
        return AgentSession(agent_id=self.id, role=request.role)

    async def continue_session(
        self, session: AgentSession, request: AgentRequest
    ) -> AgentResult:
        command = self.build_command(request)
        # Preferir path absoluto do detect() — evita WinError 2 quando o PATH
        # do processo MCP não resolve nomes nus (.CMD / PATHEXT).
        status = self.detect()
        if status.path and command:
            command = [status.path, *command[1:]]
        started = datetime.now(timezone.utc).isoformat()
        # Request é autoridade (TaskService já aplicou policies + remaining budget).
        # Profile só entra se o request não trouxer valor útil.
        if request.timeout_s and int(request.timeout_s) > 0:
            timeout = int(request.timeout_s)
        else:
            timeout = int(self.profile.get("timeout_default_s") or 1800)
        result = self.executor.run(
            command,
            cwd=Path(request.cwd),
            timeout_s=timeout,
            env=request.env,
        )
        success_code = 0
        exit_codes = self.profile.get("exit_codes") or {}
        if "success" in exit_codes:
            success_code = int(exit_codes["success"])
        status = "completed"
        if result.timed_out:
            status = "timeout"
        elif result.exit_code != success_code:
            status = "failed"
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status=status,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            stdout=result.stdout,
            stderr=result.stderr,
            model=request.model,
            command=command,
            cwd=result.cwd,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_s=result.duration_s,
        )


class FakeAgentAdapter(AgentAdapter):
    """Adapter determinístico para testes CI."""

    def __init__(self, agent_id: str, project_path: Path) -> None:
        self.id = agent_id
        self.kind = "fake"
        self.project_path = project_path

    def detect(self) -> AgentStatus:
        return AgentStatus(
            id=self.id, available=True, kind="fake", verified=True, path="fake"
        )

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            roles=["planner", "executor", "validator"],
            languages=["python"],
            can_write=True,
            can_test=False,
            can_validate=True,
            executable=True,
        )

    async def start(self, request: AgentRequest) -> AgentSession:
        return AgentSession(agent_id=self.id, role=request.role)

    async def continue_session(
        self, session: AgentSession, request: AgentRequest
    ) -> AgentResult:
        changed: list[str] = []
        stdout = f"[fake:{self.id}] role={request.role}\n"
        if request.role == "planner":
            stdout += "plan: create soma module with tests and docs\n"
        elif request.role in {"executor", "corrector"}:
            changed = self._write_soma_module()
            stdout += "wrote soma module and tests\n"
        elif request.role == "validator":
            stdout += json.dumps(
                {
                    "status": "approved",
                    "score": 0.95,
                    "blocking_issues": [],
                    "summary": "fake validation ok",
                }
            )
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="completed",
            exit_code=0,
            stdout=stdout,
            command=["fake", self.id, request.role],
            cwd=str(self.project_path),
            changed_files=changed,
            duration_s=0.01,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    def _write_soma_module(self) -> list[str]:
        pkg = self.project_path / "soma"
        pkg.mkdir(exist_ok=True)
        (pkg / "__init__.py").write_text(
            '"""Modulo soma."""\nfrom .core import soma\n\n__all__ = ["soma"]\n',
            encoding="utf-8",
        )
        (pkg / "core.py").write_text(
            '"""Operacoes aritmeticas."""\n\n\ndef soma(a: float, b: float) -> float:\n'
            '    """Retorna a + b."""\n    return a + b\n',
            encoding="utf-8",
        )
        # Garante descoberta do pacote pelo pytest
        if not (self.project_path / "pyproject.toml").exists():
            (self.project_path / "pyproject.toml").write_text(
                '[project]\nname = "fixture-soma"\nversion = "0.0.1"\n'
                'requires-python = ">=3.11"\n',
                encoding="utf-8",
            )
        tests = self.project_path / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_soma.py").write_text(
            "from soma import soma\n\n\ndef test_soma():\n    assert soma(2, 3) == 5\n",
            encoding="utf-8",
        )
        readme = self.project_path / "README.md"
        if not readme.exists():
            readme.write_text("# Fixture\n\n", encoding="utf-8")
        text = readme.read_text(encoding="utf-8")
        if "soma(" not in text:
            readme.write_text(
                text
                + "\n## Uso do modulo soma\n\n```python\nfrom soma import soma\nprint(soma(1, 2))\n```\n",
                encoding="utf-8",
            )
        return [
            "soma/__init__.py",
            "soma/core.py",
            "tests/test_soma.py",
            "README.md",
        ]


def load_profile(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
