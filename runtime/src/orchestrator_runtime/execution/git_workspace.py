"""Detecção de arquivos alterados via git (fallback quando o CLI não reporta)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# git status pode pendurar no Windows (index.lock, credential prompt, drive de
# rede). Sem timeout, a task fica presa em RECEIVED segurando o WriteLock.
GIT_TIMEOUT_S = 30


@dataclass
class GitBaseline:
    """Snapshot de ``git status --porcelain`` no início da task."""

    porcelain: dict[str, str] = field(default_factory=dict)
    available: bool = False


def _run_git(project_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    try:
        return subprocess.run(
            command,
            cwd=str(project_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout="",
            stderr=f"git timeout after {GIT_TIMEOUT_S}s",
        )


def _parse_porcelain(stdout: str) -> dict[str, str]:
    """Mapeia path -> código XY (2 chars) do porcelain v1."""
    mapping: dict[str, str] = {}
    for line in stdout.splitlines():
        if len(line) < 4:
            continue
        # Formato: XY PATH  ou  XY ORIG -> PATH (rename)
        code = line[:2]
        rest = line[3:]
        if " -> " in rest:
            path = rest.split(" -> ", 1)[1].strip()
        else:
            path = rest.strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if path:
            mapping[path.replace("\\", "/")] = code
    return mapping


def capture_baseline(project_path: Path) -> GitBaseline:
    """Captura status git atual; ``available=False`` se não for um repo git."""
    probe = _run_git(project_path, "rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or (probe.stdout or "").strip() != "true":
        return GitBaseline(available=False)
    status = _run_git(project_path, "status", "--porcelain")
    if status.returncode != 0:
        return GitBaseline(available=False)
    return GitBaseline(
        porcelain=_parse_porcelain(status.stdout or ""),
        available=True,
    )


def changed_files_since(project_path: Path, baseline: GitBaseline) -> list[str]:
    """Paths cujo status porcelain mudou (ou são novos) desde o baseline."""
    if not baseline.available:
        return []
    status = _run_git(project_path, "status", "--porcelain")
    if status.returncode != 0:
        return []
    current = _parse_porcelain(status.stdout or "")
    out: list[str] = []
    for path, code in current.items():
        if path not in baseline.porcelain or baseline.porcelain[path] != code:
            out.append(path)
    return sorted(out)
