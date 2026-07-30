"""Descoberta e execução de testes determinísticos."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from orchestrator_runtime.agents.process import CliExecutor, which


@dataclass
class DiscoveredTest:
    command: list[str]
    category: str
    source: str


def _dotnet_target(project_path: Path) -> str | None:
    """Arquivo de solucao/projeto explicito para `dotnet test` (bug-062).

    Preferencia: .sln (formato classico) > .slnx (novo no .NET 10) > .csproj.
    Nome ordenado para resultado deterministico quando ha mais de um.
    """
    for pat in ("*.sln", "*.slnx", "*.csproj"):
        matches = sorted(p.name for p in project_path.glob(pat))
        if matches:
            return matches[0]
    return None


def _npm_test_script(cwd: Path) -> str | None:
    """Script `test` do package.json — para detectar harness em modo watch."""
    import json

    try:
        data = json.loads((cwd / "package.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    scripts = data.get("scripts") or {}
    test = scripts.get("test")
    return str(test) if test else None


class TestDiscovery:
    @staticmethod
    def _is_python_project(project_path: Path) -> bool:
        """Marcador Python real — sem varrer **/test_*.py (em repos Node isso
        apanha node_modules e inventa pytest em projeto Angular; era o bug do
        validator pedindo pytest no PrintBee). `tests/` só conta com .py dentro."""
        if any(
            (project_path / f).is_file()
            for f in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
        ):
            return True
        tests_dir = project_path / "tests"
        if tests_dir.is_dir() and any(tests_dir.rglob("*.py")):
            return True
        return any(project_path.glob("test_*.py"))

    def discover(self, project_path: Path) -> list[DiscoveredTest]:
        found: list[DiscoveredTest] = []
        if (project_path / "package.json").is_file():
            found.append(
                DiscoveredTest(["npm", "test"], "unit", "package.json")
            )
        if self._is_python_project(project_path):
            if which("pytest"):
                found.append(
                    DiscoveredTest(["pytest", "-q"], "unit", "pytest")
                )
            else:
                found.append(
                    DiscoveredTest(
                        ["python", "-m", "pytest", "-q"], "unit", "python -m pytest"
                    )
                )
        if (project_path / "Cargo.toml").is_file():
            found.append(DiscoveredTest(["cargo", "test"], "unit", "Cargo.toml"))
        if (project_path / "go.mod").is_file():
            # bug-054 — `-short` honra testing.Short(): testes live/integração
            # (rede, certs mTLS) pulam. Sem isso, TestLive_* falhava offline e
            # o portão bloqueava toda iteração por ambiente (TestLive_OAuthMTLS_DES
            # na task ff270e3ff814, GuardLine). Testes unitários rodam normal.
            found.append(DiscoveredTest(["go", "test", "-short", "./..."], "unit", "go.mod"))
        dotnet_target = _dotnet_target(project_path)
        if dotnet_target:
            # bug-062 — .NET 10 preview recusa `dotnet test` sem argumento
            # mesmo com UM .sln na pasta quando ha .csproj em subdirs
            # (MSB1011, reproduzido no corehub com SDK 10.0.400-preview).
            # Alvo explicito resolve na hora — e cobre o formato novo .slnx.
            found.append(
                DiscoveredTest(["dotnet", "test", dotnet_target], "unit", "dotnet")
            )
        if (project_path / "pom.xml").is_file():
            found.append(DiscoveredTest(["mvn", "test"], "unit", "pom.xml"))
        if (project_path / "build.gradle").is_file() or (
            project_path / "build.gradle.kts"
        ).is_file():
            found.append(DiscoveredTest(["gradle", "test"], "unit", "gradle"))
        if (project_path / "Makefile").is_file():
            text = (project_path / "Makefile").read_text(encoding="utf-8", errors="ignore")
            if "test:" in text:
                found.append(DiscoveredTest(["make", "test"], "unit", "Makefile"))
        return found

    _SUBDIR_SKIP = frozenset(
        {
            "node_modules", "bin", "obj", "dist", "build", "out", "target",
            "vendor", "packages", ".git", ".hg", ".svn", "__pycache__",
            ".orchestrator", ".wolf", ".codegraph", "graphify-out",
        }
    )
    _SUBDIR_MARKERS = (
        "package.json", "pyproject.toml", "setup.py", "requirements.txt",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "Makefile",
    )

    def discover_subdirs(self, project_path: Path, max_depth: int = 2) -> list[str]:
        """Subdiretórios (até ``max_depth``) que têm marcador de stack próprio.

        bug-056 — projetos com a stack fora da raiz (printbee: src/backend,
        src/frontend) ficavam sem teste nenhum. Varredura limitada: pula
        dirs ocultos e de ruído (node_modules, bin, obj...), não desce em
        repo filho com .git (esses entram via extra_dirs do bug-048).
        """
        found: list[str] = []
        root = project_path.resolve()

        def _has_marker(d: Path) -> bool:
            if any((d / m).is_file() for m in self._SUBDIR_MARKERS):
                return True
            if list(d.glob("*.sln")) or list(d.glob("*.slnx")) or list(d.glob("*.csproj")):
                return True
            tests_dir = d / "tests"
            return tests_dir.is_dir() and any(tests_dir.rglob("*.py"))

        def _walk(d: Path, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                children = sorted(d.iterdir())
            except OSError:
                return
            for child in children:
                if not child.is_dir():
                    continue
                name = child.name
                if name.startswith(".") or name.lower() in self._SUBDIR_SKIP:
                    continue
                if (child / ".git").exists():
                    continue
                if _has_marker(child):
                    found.append(str(child.relative_to(root)).replace("\\", "/"))
                    continue  # não desce abaixo de um diretório com stack própria
                _walk(child, depth + 1)

        _walk(project_path, 1)
        return found


def stack_test_commands(project_path: Path) -> list[str]:
    """Comandos de teste da stack detectada — para injetar nos prompts de
    executor/validator e impedir harness inventado (pytest em Angular)."""
    return [" ".join(t.command) for t in TestDiscovery().discover(project_path)]


class TestRunner:
    def __init__(self, executor: CliExecutor) -> None:
        self.executor = executor

    def run_all(
        self, project_path: Path, extra_dirs: list[str] | None = None
    ) -> list[dict]:
        """Descobre e roda testes na raiz e em ``extra_dirs`` (bug-048).

        Em workspace pasta-mãe de repos aninhados (GuardLine.BR), a raiz não
        tem marcador de stack nenhum — a descoberta devolvia "<none>" e o
        validador reprovava tests_pass por falta de evidência, mesmo com o
        trabalho feito num repo filho. ``extra_dirs`` são os repos filhos
        tocados pelos changed_files da iteração.
        """
        discovery = TestDiscovery()
        tests: list[tuple[DiscoveredTest, Path]] = [
            (t, project_path) for t in discovery.discover(project_path)
        ]
        for sub in extra_dirs or []:
            sub_path = project_path / sub
            if not sub_path.is_dir():
                continue
            for t in discovery.discover(sub_path):
                tests.append(
                    (
                        DiscoveredTest(
                            command=t.command,
                            category=t.category,
                            source=f"{sub}/{t.source}",
                        ),
                        sub_path,
                    )
                )
        if not tests:
            # bug-056 — raiz sem marcador E sem repos filhos: projeto com a
            # stack em subdiretórios comuns (printbee: src/backend .NET +
            # src/frontend Angular). Sem este fallback toda task rodava com
            # teste "<none>/skipped" — portão de testes cego para sempre.
            for sub in discovery.discover_subdirs(project_path):
                sub_path = project_path / sub
                for t in discovery.discover(sub_path):
                    tests.append(
                        (
                            DiscoveredTest(
                                command=t.command,
                                category=t.category,
                                source=f"{sub}/{t.source}",
                            ),
                            sub_path,
                        )
                    )
        results = []
        if not tests:
            results.append(
                {
                    "command": "<none>",
                    "category": "unit",
                    "exit_code": None,
                    "duration_s": 0.0,
                    "stdout": "",
                    "stderr": "",
                    "status": "skipped",
                    "discovery_source": "none",
                    "failure_kind": "not_executed",
                }
            )
            return results
        for spec, cwd in tests:
            started = time.monotonic()
            # bug-050 — ferramenta ausente NÃO é teste falho. Sem pre-flight,
            # `go`/`make` fora do PATH (ou inexistente na máquina) voltava 127
            # do CliExecutor e virava failure_kind "introduced" + TEST-FAIL
            # bloqueante: a task reprovava por ambiente, não por mérito, até o
            # same_issue_repeat_limit — mesmo com o validador aprovando (1.0).
            # Medido na task 3b56b92278e9 da GuardLine: make não existe na
            # máquina e o go.mod/Makefile do repo filho (bug-048) passaram a
            # descobrir comandos impossíveis de executar.
            exe0 = spec.command[0] if spec.command else ""
            if exe0 and which(exe0) is None:
                results.append(
                    {
                        "command": " ".join(spec.command),
                        "category": spec.category,
                        "exit_code": None,
                        "duration_s": 0.0,
                        "stdout": "",
                        "stderr": (
                            f"ferramenta ausente no PATH: {exe0!r} — teste não "
                            "executado (erro de ambiente, não falha de mérito)"
                        ),
                        "status": "skipped",
                        "discovery_source": spec.source,
                        "failure_kind": "tool_missing",
                    }
                )
                continue
            # bug-063 — `npm test` sem node_modules: dependencias nunca
            # instaladas neste checkout; o script morre em <1s ("'stencil'
            # nao e reconhecido") e era cobrado como merito (failure_kind
            # "introduced") ate derrubar a task. Ambiente, nao merito.
            if exe0 == "npm" and not (cwd / "node_modules").is_dir():
                results.append(
                    {
                        "command": " ".join(spec.command),
                        "category": spec.category,
                        "exit_code": None,
                        "duration_s": 0.0,
                        "stdout": "",
                        "stderr": (
                            f"node_modules ausente em {cwd} — rode `npm install`; "
                            "teste nao executado (erro de ambiente, nao falha de merito)"
                        ),
                        "status": "skipped",
                        "discovery_source": spec.source,
                        "failure_kind": "deps_missing",
                    }
                )
                continue
            try:
                env = {"PYTHONPATH": str(cwd)}
                command = list(spec.command)
                # bug-063 — `ng test` sem --watch=false entra em modo watch
                # (Karma) e nunca sai: build quebrado (TS18003) segurou o
                # processo 601s ate o timeout, 2x por task = 20min queimados
                # no corehub. O flag converte em falha rapida e honesta.
                if exe0 == "npm":
                    script = _npm_test_script(cwd)
                    if script and "ng test" in script and "--watch" not in script:
                        command = [*command, "--", "--watch=false"]
                result = self.executor.run(
                    command,
                    cwd=cwd,
                    timeout_s=600,
                    env=env,
                    allow_nested=True,
                )
                status = "passed" if result.exit_code == 0 and not result.timed_out else "failed"
                failure_kind = None
                if status == "failed":
                    failure_kind = "introduced"
                results.append(
                    {
                        "command": " ".join(command),
                        "category": spec.category,
                        "exit_code": result.exit_code,
                        "duration_s": time.monotonic() - started,
                        "stdout": result.stdout[-8000:],
                        "stderr": result.stderr[-8000:],
                        "status": "timeout" if result.timed_out else status,
                        "discovery_source": spec.source,
                        "failure_kind": failure_kind,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "command": " ".join(spec.command),
                        "category": spec.category,
                        "exit_code": None,
                        "duration_s": time.monotonic() - started,
                        "stdout": "",
                        "stderr": str(exc),
                        "status": "failed",
                        "discovery_source": spec.source,
                        "failure_kind": "environment",
                    }
                )
        return results
