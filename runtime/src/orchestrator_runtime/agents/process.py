"""Executor de processos CLI (compartilhado com dispatch)."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator_runtime.errors import PathEscapeError, RecursionBlockedError


SECRET_PATTERNS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION")


def sanitize_env(env: dict[str, str] | None = None) -> dict[str, str]:
    base = dict(os.environ)
    if env:
        base.update(env)
    # Nunca propaga valores sensíveis para logs; mantém no processo filho.
    return base


def redact(text: str) -> str:
    # Evita gravar linhas que parecem secrets.
    lines = []
    for line in text.splitlines():
        upper = line.upper()
        if any(p in upper for p in SECRET_PATTERNS) and ("=" in line or ":" in line):
            lines.append("[REDACTED]")
        else:
            lines.append(line)
    return "\n".join(lines)


def assert_within_project(path: Path, project: Path) -> Path:
    resolved = path.resolve()
    project_resolved = project.resolve()
    try:
        resolved.relative_to(project_resolved)
    except ValueError as exc:
        raise PathEscapeError(
            f"Caminho fora do projeto: {resolved} (projeto={project_resolved})"
        ) from exc
    return resolved


@dataclass
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_s: float = 0.0
    command: list[str] = field(default_factory=list)
    cwd: str | None = None


class CliExecutor:
    """Executa CLI com lista de argumentos, timeout e anti-recursão."""

    def __init__(self, project_path: Path, echo: bool = True) -> None:
        self.project_path = project_path.resolve()
        self.echo = echo

    def run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        timeout_s: int = 600,
        env: dict[str, str] | None = None,
        heartbeat_s: int = 30,
        allow_nested: bool = False,
    ) -> ProcessResult:
        if not allow_nested and os.environ.get("ORCHESTRATOR_CHILD_AGENT"):
            raise RecursionBlockedError(
                "ORCHESTRATOR_CHILD_AGENT presente: agente filho nao pode delegar."
            )
        workdir = assert_within_project(cwd or self.project_path, self.project_path)
        merged = sanitize_env(env)
        previous = os.environ.get("ORCHESTRATOR_CHILD_AGENT")
        merged["ORCHESTRATOR_CHILD_AGENT"] = "1"

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        started = time.monotonic()
        timed_out = False

        if self.echo:
            print(f"[exec] {redact(' '.join(command))}", flush=True)

        proc = subprocess.Popen(
            command,
            cwd=str(workdir),
            env=merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        stop_heartbeat = threading.Event()

        def _reader(stream, chunks: list[str], prefix: str) -> None:
            assert stream is not None
            for line in stream:
                chunks.append(line)
                if self.echo:
                    print(f"{prefix}{redact(line.rstrip(chr(10) + chr(13)))}", flush=True)

        def _heartbeat() -> None:
            while not stop_heartbeat.wait(heartbeat_s):
                elapsed = int(time.monotonic() - started)
                print(f"[heartbeat] running {elapsed}s pid={proc.pid}", flush=True)

        t_out = threading.Thread(
            target=_reader, args=(proc.stdout, stdout_chunks, "  > "), daemon=True
        )
        t_err = threading.Thread(
            target=_reader, args=(proc.stderr, stderr_chunks, "  ! "), daemon=True
        )
        t_hb = threading.Thread(target=_heartbeat, daemon=True)
        t_out.start()
        t_err.start()
        t_hb.start()

        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_tree(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        finally:
            stop_heartbeat.set()
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            if previous is None:
                os.environ.pop("ORCHESTRATOR_CHILD_AGENT", None)
            else:
                os.environ["ORCHESTRATOR_CHILD_AGENT"] = previous

        duration = time.monotonic() - started
        return ProcessResult(
            exit_code=(-1 if timed_out else (proc.returncode or 0)),
            stdout=redact("".join(stdout_chunks)),
            stderr=redact("".join(stderr_chunks)),
            timed_out=timed_out,
            duration_s=duration,
            command=command,
            cwd=str(workdir),
        )

    @staticmethod
    def _kill_tree(pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.kill(pid, 9)
            except OSError:
                pass


def which(name: str) -> str | None:
    from shutil import which as _which

    return _which(name)
