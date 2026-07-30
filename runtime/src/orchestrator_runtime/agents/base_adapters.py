"""Adaptador CLI genérico baseado em profile JSON."""

from __future__ import annotations

import json
import os
import subprocess
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

# Windows: CreateProcess corta a linha de comando em 32767 chars. A margem cobre
# aspas e o executavel resolvido por path absoluto. Em POSIX o teto e ~2MB, mas
# um prompt desse tamanho vai por stdin nos dois — um caminho so.
ARGV_LIMIT = 30000

# cmd.exe processa .CMD/.BAT com teto proprio de 8191 chars por linha — muito
# abaixo dos 32767 do CreateProcess. bug-061 (corehub, 0.4.40): prompt de 9635
# chars para codex.CMD morria no spawn com "Linha de comando muito longa."
# (exit 1, 29 bytes de stderr) ANTES de o agente iniciar; executor E corrector
# zerados e a task INCOMPLETE sem trabalho. Reproduzido: 8100 passa, 8200 falha.
CMD_ARGV_LIMIT = 8000


def _argv_len(argv: list[str]) -> int:
    # +1 por argumento: o separador que o Windows conta ao montar a linha.
    return sum(len(a) + 1 for a in argv)


def _effective_argv_limit(argv: list[str]) -> int:
    """Teto real da linha de comando conforme o executavel resolvido."""
    exe0 = str(argv[0]).lower() if argv else ""
    if exe0.endswith((".cmd", ".bat")):
        return CMD_ARGV_LIMIT
    return ARGV_LIMIT


def _cmdline_len(argv: list[str]) -> int:
    """Tamanho da linha apos quoting — e ela que CreateProcess/cmd.exe contam,
    nao a soma crua dos argumentos (prompt com aspas/espacos incha no escape)."""
    if os.name == "nt":
        try:
            return len(subprocess.list2cmdline([str(a) for a in argv]))
        except Exception:  # noqa: BLE001
            pass
    return _argv_len(argv)


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

    def build_command(
        self, request: AgentRequest, *, prompt_in_argv: bool = True
    ) -> list[str]:
        invoke = self.profile.get("invoke") or {}
        args: list[str] = [self.id]
        for part in invoke.get("subcommand") or []:
            args.append(str(part))
        # Flags de sandbox/automação do profile (ex.: codex --full-auto).
        # 0.4.15: no Windows, CreateProcessAsUserW falha com erro 740 quando
        # --sandbox workspace-write é usado (requer elevação); override para
        # danger-full-access. Profile base mantém workspace-write (documentado).
        sandbox_flags = list(invoke.get("sandbox_flags") or [])
        if os.name == "nt" and "--sandbox" in sandbox_flags:
            idx = sandbox_flags.index("--sandbox")
            if idx + 1 < len(sandbox_flags) and sandbox_flags[idx + 1] == "workspace-write":
                sandbox_flags[idx + 1] = "danger-full-access"
        for part in sandbox_flags:
            args.append(str(part))
        if request.model and request.model_flag:
            args.extend([request.model_flag, request.model])
        elif request.model and self.profile.get("model_flag"):
            args.extend([str(self.profile["model_flag"]), request.model])
        prompt_flag = invoke.get("prompt_flag", None)
        # JSON null -> None; missing key defaults to -p for safety only if documented
        if "prompt_flag" in invoke:
            prompt_flag = invoke.get("prompt_flag")
        # prompt_in_argv=False: o prompt vai pelo stdin (ver ARGV_LIMIT abaixo).
        # `codex exec` e `claude -p` leem stdin quando nao recebem o texto —
        # e o mesmo caminho que ja imprimia "Reading additional input from
        # stdin..." quando o stdin era DEVNULL.
        if prompt_flag:
            args.append(str(prompt_flag))
            if prompt_in_argv:
                args.append(request.prompt)
        elif prompt_in_argv:
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
        # 0.4.29 (bug-041) — Windows corta a linha de comando em 32767 chars e o
        # Popen morre com "Linha de comando muito longa" ANTES de o agente rodar:
        # 30 bytes de saida, zero arquivo tocado, e a task ainda seguia para
        # validacao como se tivesse executado. Desde a 0.4.27 o prompt carrega
        # skills + rules + loop, entao passou a estourar com prompt de usuario a
        # partir de ~6KB. Medido no printbee: 2 tasks, executor E corrector.
        stdin_text: str | None = None
        invoke = self.profile.get("invoke") or {}
        prompt_via = str((invoke.get("prompt_via") or "arg")).lower()
        # Nem todo CLI le o prompt do stdin. `kimi -p <prompt>` EXIGE o valor:
        # remover o texto deixaria um `-p` vazio e o CLI recusaria o comando.
        # Nesse caso o pre-flight abaixo falha com diagnostico proprio em vez
        # de entregar o erro criptico do cmd.exe/CreateProcess.
        stdin_ok = invoke.get("prompt_stdin", True) is not False
        limit = _effective_argv_limit(command)
        if stdin_ok and (prompt_via == "stdin" or _cmdline_len(command) > limit):
            command = self.build_command(request, prompt_in_argv=False)
            if status.path and command:
                command = [status.path, *command[1:]]
            stdin_text = request.prompt
        # bug-061 — sem stdin e linha acima do teto do executavel: falhar com
        # explicacao clara. O caminho antigo entregava o erro cru do cmd.exe
        # ("Linha de comando muito longa.", exit 1) e a task seguia para
        # validacao como se o agente tivesse trabalhado.
        if stdin_text is None and _cmdline_len(command) > limit:
            now = datetime.now(timezone.utc).isoformat()
            return AgentResult(
                session_id=session.id,
                agent_id=self.id,
                role=request.role,
                status="failed",
                exit_code=126,
                stderr=(
                    f"[argv-overflow] linha de comando com {_cmdline_len(command)} "
                    f"chars excede o teto de {limit} do executavel {command[0]!r} "
                    "(.CMD/.BAT passam pelo cmd.exe, teto 8191). Este CLI nao "
                    "aceita prompt por stdin (invoke.prompt_stdin=false); "
                    "encurte o prompt ou ajuste o profile."
                ),
                model=request.model,
                command=command,
                cwd=str(request.cwd),
                started_at=started,
                finished_at=now,
            )
        result = self.executor.run(
            command,
            cwd=Path(request.cwd),
            timeout_s=timeout,
            env=request.env,
            stdin_text=stdin_text,
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
