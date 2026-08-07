"""Executor de processos CLI (compartilhado com dispatch)."""

from __future__ import annotations

import os
import re
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


# bug-086 — agente MUDO come o orcamento inteiro da task. GuardLine
# e0457603df65 (2026-08-06): executor claude/opus ficou 40 min com ZERO bytes
# em stdout E stderr e so morreu no timeout do papel (2400s); o corrector que
# entrou depois estava trabalhando de verdade (20KB de stderr, arquivos sendo
# escritos) e foi morto 17 min depois pelo maximum_duration_seconds da task.
# Resultado: 1h gasta, INCOMPLETE, nada entregue — e o agente que produzia foi
# justamente o sacrificado. O marcador vai no stderr (mesmo padrao do
# INFRA-FAIL-FAST) para o service distinguir "pendurado" de "timeout normal".
NO_OUTPUT_MARKER = "[NO-OUTPUT-WATCHDOG]"


SECRET_PATTERNS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION")


def sanitize_env(env: dict[str, str] | None = None) -> dict[str, str]:
    base = dict(os.environ)
    if env:
        base.update(env)
    # Nunca propaga valores sensíveis para logs; mantém no processo filho.
    return base


def is_child_agent(env: dict[str, str] | None = None) -> bool:
    """Flag de filho é VALOR, não presença (bug-057).

    Shells herdam ``ORCHESTRATOR_CHILD_AGENT=`` vazia (``export VAR=`` num
    wrapper) e o agente principal se achava delegado — recusava orquestrar e
    fazia tudo inline. Vazia ou ``0`` = não é filho; o runtime seta ``1``.
    """
    src = os.environ if env is None else env
    return (src.get("ORCHESTRATOR_CHILD_AGENT") or "").strip() not in ("", "0")


# bug-088 — a redação apagava a LINHA INTEIRA sempre que ela citasse a palavra
# "secret"/"token"/"password" e tivesse ':' ou '='. Isso destruiu a saída do
# decompositor na primeira execução real do fan-out (task 143e8b2ca47b): o JSON
# das subtarefas mencionava "NAO exponha secrets" e voltou como
# {"subtasks":[ [REDACTED] [REDACTED] ]} — o parse achou zero subtarefas e o
# runtime caiu no sequencial sem que ninguém percebesse. E não é só log:
# `run()` devolve o texto redigido, então o próprio runtime PARSEIA o que
# sobrou. Tarefa de documentação, de segurança ou de config fala dessas
# palavras o tempo todo.
#
# Agora redige o VALOR, não a linha, e só quando a forma é de atribuição de
# segredo: chave sem espaços contendo o marcador, separador, e valor colado
# que pareça segredo (longo, ou com dígito/pontuação). Prosa sobrevive.
_SECRET_ASSIGN_RE = re.compile(
    r"""(?ix)
    (?P<key>[\w.\-\[\]]*
        (?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD|AUTHORIZATION)
        [\w.\-\[\]]*)
    (?P<sep>["']?\s*[:=]\s*["']?)
    (?P<value>[^\s"',;}\]]+)
    """
)
_PLACEHOLDER_VALUES = {
    "null", "none", "true", "false", "nome", "valor", "value",
    "xxx", "...", "***", "redacted", "obrigatorio", "opcional",
}


def _looks_secret(value: str) -> bool:
    """Só descarta placeholder — na dúvida, redige.

    Tentei exigir forma de segredo (comprimento, dígito) e isso deixou passar
    `API_KEY=supersecret`, que é segredo de verdade. Como agora some o VALOR e
    não a linha, redigir demais custa uma palavra ilegível; redigir de menos
    vaza credencial. O desempate é óbvio.
    """
    if value.lower() in _PLACEHOLDER_VALUES:
        return False
    return not (value.startswith("<") or value.startswith("${"))


def redact(text: str) -> str:
    """Esconde valores de segredo preservando o resto da linha."""

    def _sub(match: re.Match[str]) -> str:
        if not _looks_secret(match.group("value")):
            return match.group(0)
        return f"{match.group('key')}{match.group('sep')}[REDACTED]"

    return "\n".join(_SECRET_ASSIGN_RE.sub(_sub, line) for line in text.splitlines())


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
        heartbeat_s: int = 30,
    ) -> None:
        self.project_path = project_path.resolve()
        self.echo = echo
        # 0.4.29 — cadencia do sinal de vida, vinda do perfil de quem chamou:
        # superficie bloqueante fica muda entre um heartbeat e outro, entao bate
        # mais rapido; quem faz polling le o banco no proprio ritmo.
        self.heartbeat_s = heartbeat_s
        # 0.4.15: matar processo após este nº de marcadores de infra consecutivos
        # (740 / sandbox Windows). 0 desabilita o fail-fast.
        self.infra_fail_fast_count = infra_fail_fast_count
        # PIDs de CLIs em execução — alvo do cancel (kill de filhos).
        self._active_pids: set[int] = set()
        # 0.4.28 — callback de progresso: sem isto o heartbeat so existia no
        # console do processo que chamou, entao quem observa por MCP/DB via a
        # task parada em EXECUTING por 10-30min e concluia que travou.
        self.on_heartbeat = None
        # bug-086 — watchdog de silencio. Atributos (nao parametros de run())
        # pelo mesmo motivo do on_heartbeat: os adapters chamam run() e nao
        # precisam saber que isto existe. 0 desliga.
        self.no_output_timeout_s = 0
        # Sonda de progresso EXTERNO: `claude -p` so imprime no fim, entao
        # silencio sozinho nao prova travamento — o que prova e silencio + zero
        # mudanca no workspace. Callable[[], bool]: True = ha trabalho novo.
        self.progress_probe = None

    def run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        timeout_s: int = 600,
        env: dict[str, str] | None = None,
        heartbeat_s: int | None = None,
        allow_nested: bool = False,
        stdin_text: str | None = None,
    ) -> ProcessResult:
        if heartbeat_s is None:
            heartbeat_s = self.heartbeat_s
        if not allow_nested and is_child_agent():
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
        # bug-086: instante do ultimo sinal de vida (byte lido ou progresso no
        # workspace). Comeca no spawn — agente que nunca falou conta desde ja.
        last_signal = [started]
        no_output_exit = threading.Event()

        if self.echo:
            _live(f"[exec] {redact(' '.join(resolved_command))}")

        try:
            # stdin=DEVNULL: CLIs como `codex exec` leem prompt do stdin se
            # herdarem pipe/TTY vazio ("Reading additional input from stdin...").
            # 0.4.29: com stdin_text esse mesmo caminho vira o canal do prompt,
            # para argv nao estourar o teto de 32767 chars do Windows (bug-041).
            proc = subprocess.Popen(
                resolved_command,
                cwd=str(workdir),
                env=merged,
                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
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
            if winerr == 206:
                # ERROR_FILENAME_EXCED_RANGE — "Linha de comando muito longa".
                # 0.4.29: o prompt grande passou a ir por stdin, mas se algo
                # ainda estourar o teto o erro tem que se explicar: antes vinham
                # 30 bytes crus e a task seguia para validacao como se tivesse
                # executado.
                detail = (
                    f"[WinError 206] linha de comando excede o limite do Windows "
                    f"(32767): {sum(len(a) + 1 for a in resolved_command)} chars em "
                    f"{len(resolved_command)} argumentos. O prompt deveria ter ido "
                    f"por stdin (invoke.prompt_via). original={exc}"
                )
                return ProcessResult(
                    exit_code=126,
                    stdout="",
                    stderr=detail,
                    timed_out=False,
                    duration_s=time.monotonic() - started,
                    command=resolved_command,
                    cwd=str(workdir),
                )
            raise

        if stdin_text is not None and proc.stdin is not None:
            # Escrever e FECHAR: o CLI so comeca a trabalhar ao ver EOF. Falha
            # aqui (pipe quebrado) nao derruba a execucao — o agente ja morreu
            # e o exit code conta a historia.
            try:
                proc.stdin.write(stdin_text)
                proc.stdin.close()
            except OSError:
                pass

        self._active_pids.add(proc.pid)
        stop_heartbeat = threading.Event()

        def _reader(stream, chunks: list[str], prefix: str) -> None:
            assert stream is not None
            for line in stream:
                chunks.append(line)
                last_signal[0] = time.monotonic()
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

        def _no_output_watchdog() -> None:
            limit = int(self.no_output_timeout_s or 0)
            if limit <= 0:
                return
            # Acorda com frequencia bem maior que o limite para nao atrasar o
            # kill por ate uma janela inteira.
            tick = max(5, min(30, limit // 4 or 5))
            while not stop_heartbeat.wait(tick):
                if time.monotonic() - last_signal[0] < limit:
                    continue
                probe = self.progress_probe
                if probe is not None:
                    try:
                        if probe():
                            # Escreveu no workspace: esta vivo, so calado.
                            last_signal[0] = time.monotonic()
                            continue
                    except Exception:  # noqa: BLE001
                        # Sonda quebrada NUNCA mata agente: sem prova, sem kill.
                        last_signal[0] = time.monotonic()
                        continue
                if proc.poll() is not None:
                    return  # terminou sozinho na janela: nao ha o que matar
                no_output_exit.set()
                self._kill_tree(proc.pid)
                return

        t_out = threading.Thread(
            target=_reader, args=(proc.stdout, stdout_chunks, "  > "), daemon=True
        )
        t_err = threading.Thread(
            target=_reader, args=(proc.stderr, stderr_chunks, "  ! "), daemon=True
        )
        t_hb = threading.Thread(target=_heartbeat, daemon=True)
        t_wd = threading.Thread(target=_no_output_watchdog, daemon=True)
        t_out.start()
        t_err.start()
        t_hb.start()
        t_wd.start()

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
        if no_output_exit.is_set():
            # timed_out=True para o service tratar como agente morto pelo
            # runtime; o marcador diz QUAL morte foi, porque "timeout" puro
            # levava a rotular de NO-OUTPUT ate quem tinha 20KB de saida.
            timed_out = True
            stderr_text += (
                f"\n{NO_OUTPUT_MARKER} agente morto apos "
                f"{int(self.no_output_timeout_s)}s sem NENHUMA saida e sem "
                f"tocar no workspace (duracao total {int(duration)}s)"
            )
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

    found = _which(name)
    if found:
        return found
    # bug-073 — CLIs globais fora do PATH do processo MCP: kimi-code instalou
    # em `npm prefix -g` (npm-global do desktop) e o detect() marcava kimi
    # indisponível para sempre — o roteador nunca escolhia kimi mesmo com o
    # CLI instalado (reportado pelo dono em 2026-07-30). Fallback por
    # locais bem conhecidos de bin global no Windows.
    if os.name == "nt":
        return _which_windows_fallback(name)
    return None


def _npm_global_bins_nt() -> list[Path]:
    """Dirs conhecidos de bin global npm no Windows (cache por processo)."""
    global _NPM_BINS_CACHE
    if _NPM_BINS_CACHE is not None:
        return _NPM_BINS_CACHE
    cands: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(Path(appdata) / "npm")
    try:
        import shutil

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if npm:
            out = subprocess.run(
                [npm, "prefix", "-g"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if out.returncode == 0 and out.stdout.strip():
                cands.append(Path(out.stdout.strip()))
    except Exception:  # noqa: BLE001
        pass
    _NPM_BINS_CACHE = cands
    return cands


_NPM_BINS_CACHE: list[Path] | None = None


def _which_windows_fallback(name: str) -> str | None:
    for d in _npm_global_bins_nt():
        for ext in (".cmd", ".exe", ".bat", ".ps1", ""):
            p = d / f"{name}{ext}"
            if p.is_file():
                return str(p)
    return None
