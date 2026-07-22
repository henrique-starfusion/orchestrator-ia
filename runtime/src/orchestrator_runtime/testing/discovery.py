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


class TestDiscovery:
    def discover(self, project_path: Path) -> list[DiscoveredTest]:
        found: list[DiscoveredTest] = []
        if (project_path / "package.json").is_file():
            found.append(
                DiscoveredTest(["npm", "test"], "unit", "package.json")
            )
        if (project_path / "pyproject.toml").is_file() or list(
            project_path.glob("**/test_*.py")
        ) or (project_path / "tests").is_dir():
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
            found.append(DiscoveredTest(["go", "test", "./..."], "unit", "go.mod"))
        if list(project_path.glob("*.sln")) or list(project_path.glob("*.csproj")):
            found.append(
                DiscoveredTest(["dotnet", "test"], "unit", "dotnet")
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


class TestRunner:
    def __init__(self, executor: CliExecutor) -> None:
        self.executor = executor

    def run_all(self, project_path: Path) -> list[dict]:
        discovery = TestDiscovery()
        tests = discovery.discover(project_path)
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
        for spec in tests:
            started = time.monotonic()
            try:
                env = {"PYTHONPATH": str(project_path)}
                result = self.executor.run(
                    spec.command,
                    cwd=project_path,
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
                        "command": " ".join(spec.command),
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
