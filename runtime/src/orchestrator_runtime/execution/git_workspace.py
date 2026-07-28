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
    """Snapshot de ``git status --porcelain`` no início da task.

    ``nested`` guarda o porcelain de cada repo git FILHO imediato do workspace
    (bug-047): em projetos que agrupam vários repos numa pasta-mãe (ex.:
    GuardLine.BR contém travelex-api/, onp-api/ — cada um com .git próprio),
    ``git status`` na raiz não desce no repo aninhado e todo o trabalho do
    executor ficava invisível — changed=[] sempre, workspace_changes nunca
    passava e timeout com trabalho real virava AGENT-TIMEOUT-NO-OUTPUT.
    """

    porcelain: dict[str, str] = field(default_factory=dict)
    available: bool = False
    nested: dict[str, dict[str, str]] = field(default_factory=dict)


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


def _nested_repo_dirs(project_path: Path) -> list[str]:
    """Filhos imediatos com .git próprio (dir ou arquivo de worktree).

    Só o primeiro nível: é o layout observado (pasta-mãe de repos). Descer
    mais fundo custaria um walk completo a cada agente — sem caso de uso.
    """
    out: list[str] = []
    try:
        for child in project_path.iterdir():
            if child.name == ".git" or not child.is_dir():
                continue
            if (child / ".git").exists():
                out.append(child.name)
    except OSError:
        return []
    return sorted(out)


def capture_baseline(project_path: Path) -> GitBaseline:
    """Captura status git atual; ``available=False`` se não for um repo git.

    Repos aninhados (filhos imediatos com .git) entram em ``nested`` mesmo
    quando a raiz não é repo — bug-047.
    """
    baseline = GitBaseline()
    probe = _run_git(project_path, "rev-parse", "--is-inside-work-tree")
    if probe.returncode == 0 and (probe.stdout or "").strip() == "true":
        status = _run_git(project_path, "status", "--porcelain")
        if status.returncode == 0:
            baseline.porcelain = _parse_porcelain(status.stdout or "")
            baseline.available = True
    for name in _nested_repo_dirs(project_path):
        status = _run_git(project_path / name, "status", "--porcelain")
        if status.returncode == 0:
            baseline.nested[name] = _parse_porcelain(status.stdout or "")
    return baseline


def changed_files_since(project_path: Path, baseline: GitBaseline) -> list[str]:
    """Paths cujo status porcelain mudou (ou são novos) desde o baseline.

    Inclui repos aninhados capturados no baseline, com o path prefixado pelo
    diretório do repo filho ("travelex-api/main.go").
    """
    out: set[str] = set()
    if baseline.available:
        status = _run_git(project_path, "status", "--porcelain")
        if status.returncode == 0:
            current = _parse_porcelain(status.stdout or "")
            for path, code in current.items():
                if baseline.porcelain.get(path) != code:
                    out.add(path)
    for name, base_map in baseline.nested.items():
        status = _run_git(project_path / name, "status", "--porcelain")
        if status.returncode != 0:
            continue
        current = _parse_porcelain(status.stdout or "")
        for path, code in current.items():
            if base_map.get(path) != code:
                out.add(f"{name}/{path}")
    return sorted(out)
