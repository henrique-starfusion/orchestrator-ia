"""Executor de processos CLI (compartilhado com dispatch)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator_runtime.errors import PathEscapeError, RecursionBlockedError


def _live(msg: str) -> None:
    """Echo ao vivo só em stderr — stdout é sagrado no transporte MCP stdio."""
    print(msg, file=sys.stderr, flush=True)


# Marcadores de falha de infra do sandbox do Codex no Windows.
# CreateProcessAsUserW requer elevação (erro 740) quando --sandbox workspace-write
# é usado; o Codex não aborta e entra em loop por node_repl/js indefinidamente.
# Importado por service.py (_VALIDATOR_INFRA_MARKERS).
INFRA_FAIL_MARKERS: tuple[str, ...] = (
    "createprocessasuserw failed: 740",
    "windows sandbox: runner failed",
    "windows error 740",
    # 0.4.18 — Codex preso em ritual multi-agente (printbee-patterns / collab Wait)
    "collab: wait",
    "command timed out after 124",
)


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

    def __init__(
        self,
        project_path: Path,
        echo: bool = True,
        infra_fail_fast_count: int = 3,
    ) -> None:
        self.project_path = project_path.resolve()
        self.echo = echo
        # 0.4.15: matar processo após este nº de marcadores de infra consecutivos
        # (740 / sandbox Windows). 0 desabilita o fail-fast.
        self.infra_fail_fast_count = infra_fail_fast_count
        # PIDs de CLIs em execução — alvo do cancel (kill de filhos).
        self._active_pids: set[int] = set()
        # 0.4.28 — callback de progresso: sem isto o heartbeat so existia no
        # console do processo que chamou, entao quem observa por MCP/DB via a
        # task parada em EXECUTING por 10-30min e concluia que travou.
        self.on_heartbeat = None

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

        # Windows CreateProcess não resolve PATHEXT para nomes nus (ex.: "codex");
        # shutil.which encontra "codex.CMD", mas Popen(["codex", ...]) falha com WinError 2.
        resolved_command = list(command)
        if resolved_command:
            exe = resolved_command[0]
            exe_path = Path(exe)
            if not exe_path.is_file():
                found = which(exe)
                if found:
                    resolved_command[0] = found

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        started = time.monotonic()
        timed_out = False
        # 0.4.15 fail-fast: contador total de marcadores de infra no stream.
        infra_fail_count = [0]
        infra_fast_exit = threading.Event()

        if self.echo:
            _live(f"[exec] {redact(' '.join(resolved_command))}")

        try:
            # stdin=DEVNULL: CLIs como `codex exec` leem prompt do stdin se
            # herdarem pipe/TTY vazio ("Reading additional input from stdin...").
            proc = subprocess.Popen(
                resolved_command,
                cwd=str(workdir),
                env=merged,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            # Ainda sem executável resolvido (PATH do MCP/Cursor incompleto / WinError 2).
            exe0 = resolved_command[0] if resolved_command else "?"
            which_hint = which(str(exe0)) if resolved_command else None
            detail = (
                f"[WinError 2 / FileNotFoundError] executável não encontrado: {exe0!r}. "
                f"which={which_hint!r} cwd={workdir} PATH_has_exe="
                f"{bool(which_hint)}. command={resolved_command!r}. "
                f"original={exc}"
            )
            return ProcessResult(
                exit_code=127,
                stdout="",
                stderr=detail,
                timed_out=False,
                duration_s=time.monotonic() - started,
                command=resolved_command,
                cwd=str(workdir),
            )
        except OSError as exc:
            # Windows às vezes reporta WinError 2 como OSError genérico.
            winerr = getattr(exc, "winerror", None)
            if winerr == 2 or getattr(exc, "errno", None) == 2:
                exe0 = resolved_command[0] if resolved_command else "?"
                detail = (
                    f"[WinError 2] O sistema não pode encontrar o arquivo: {exe0!r}. "
                    f"cwd={workdir} command={resolved_command!r}. original={exc}"
                )
                return ProcessResult(
                    exit_code=127,
                    stdout="",
                    stderr=detail,
                    timed_out=False,
                    duration_s=time.monotonic() - started,
                    command=resolved_command,
                    cwd=str(workdir),
                )
            raise

        self._active_pids.add(proc.pid)
        stop_heartbeat = threading.Event()

        def _reader(stream, chunks: list[str], prefix: str) -> None:
            assert stream is not None
            for line in stream:
                chunks.append(line)
                if self.echo:
                    _live(f"{prefix}{redact(line.rstrip(chr(10) + chr(13)))}")
                # 0.4.15: fail-fast — detecta marcadores de infra do sandbox Windows
                # (740/runner failed) no stream e mata o processo após N ocorrências.
                if self.infra_fail_fast_count > 0 and not infra_fast_exit.is_set():
                    lower = line.lower()
                    if any(m in lower for m in INFRA_FAIL_MARKERS):
                        infra_fail_count[0] += 1
                        if infra_fail_count[0] >= self.infra_fail_fast_count:
                            infra_fast_exit.set()
                            self._kill_tree(proc.pid)

        def _heartbeat() -> None:
            if heartbeat_s <= 0:
                return
            while not stop_heartbeat.wait(heartbeat_s):
                elapsed = int(time.monotonic() - started)
                if self.echo:
                    _live(f"[heartbeat] running {elapsed}s pid={proc.pid}")
                if self.on_heartbeat is not None:
                    try:
                        self.on_heartbeat(elapsed, proc.pid)
                    except Exception:  # noqa: BLE001
                        pass  # progresso nunca derruba a execucao

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
            self._active_pids.discard(proc.pid)
            stop_heartbeat.set()
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            if previous is None:
                os.environ.pop("ORCHESTRATOR_CHILD_AGENT", None)
            else:
                os.environ["ORCHESTRATOR_CHILD_AGENT"] = previous

        duration = time.monotonic() - started
        stderr_text = redact("".join(stderr_chunks))
        if infra_fast_exit.is_set():
            # Append marker so _validator_infra_failure (service.py) triggers fallback.
            stderr_text += (
                f"\n[INFRA-FAIL-FAST] windows sandbox: runner failed"
                f" (detected {infra_fail_count[0]}x,"
                f" killed after {self.infra_fail_fast_count} occurrences)"
            )
        return ProcessResult(
            exit_code=(-1 if timed_out else (proc.returncode or 0)),
            stdout=redact("".join(stdout_chunks)),
            stderr=stderr_text,
            timed_out=timed_out,
            duration_s=duration,
            command=resolved_command,
            cwd=str(workdir),
        )

    def kill_active(self) -> list[int]:
        """Mata as árvores de processos CLI ativos (propagação de cancel).

        ponytail: mata todos os filhos deste executor — um workflow por vez sob
        o write lock, então o alvo é a task cancelada; rastrear pid→task se um
        dia houver escrita paralela.
        """
        killed: list[int] = []
        for pid in list(self._active_pids):
            self._kill_tree(pid)
            killed.append(pid)
        return killed

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
