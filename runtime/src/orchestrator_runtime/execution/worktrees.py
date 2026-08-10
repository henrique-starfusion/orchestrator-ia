"""Worktrees git por subtarefa: escrita paralela sem árvore compartilhada.

Por que worktree e não "vários agentes na mesma pasta": bug-077 (printbee)
registrou seis quase-arrastões num único dia com agentes escrevendo lado a
lado — `git add -A` de um leva o trabalho não commitado do outro, e
`checkout .` apaga sem volta. Dentro de um worktree privado esse perigo some:
cada subtarefa tem árvore, índice e HEAD próprios, então `git add -A` ali é
seguro por construção e a fusão volta como patch explícito.

Fluxo:
    create_worktree  -> `git worktree add --detach <path> <base>`
    (agente roda com cwd=path)
    collect_patch    -> `git add -A` + `git diff --cached --binary`
    apply_patch      -> `git apply --check` e só então `git apply` na árvore real
    remove_worktree  -> `git worktree remove --force` + prune

A aplicação é tudo-ou-nada de propósito. `git apply --3way` resolveria mais
casos, mas em conflito ele deixa marcadores no working tree — ou seja, sujaria
a árvore real com um merge pela metade justamente no caminho em que já há
trabalho de outros agentes. Patch que não passa no `--check` é reportado como
conflito e a subtarefa volta para o corrector, com a árvore intacta.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from orchestrator_runtime.execution.git_workspace import run_git

# Checkout completo de HEAD: bem mais lento que um `status`.
WORKTREE_TIMEOUT_S = 300


@dataclass
class WorktreeHandle:
    subtask_id: str
    path: Path
    base_commit: str


def _sanitize(name: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in str(name)]
    return "".join(keep)[:40] or "subtask"


def git_head(project_path: Path) -> str | None:
    """SHA do HEAD, ou None se não for repo git / repo sem commit nenhum."""
    probe = run_git(project_path, "rev-parse", "--verify", "HEAD")
    if probe.returncode != 0:
        return None
    head = (probe.stdout or "").strip()
    return head or None


def worktrees_available(project_path: Path) -> bool:
    """Fan-out com escrita exige repo git com pelo menos um commit.

    Sem commit base não há de onde criar worktree nem contra o que diffar —
    o caminho paralelo simplesmente não se aplica e o runtime segue sequencial.
    """
    return git_head(project_path) is not None


def ensure_ignored(directory: Path) -> None:
    """Marca o diretório como ignorado pelo git do projeto.

    Sem isto, projeto que VERSIONA `.orchestrator/` (printbee, adzora,
    trustsafe hoje) veria a árvore inteira do worktree como arquivos novos —
    e um `git add -A` de agente commitaria um clone do repo dentro do repo.
    `.gitignore` com `*` no diretório resolve na origem.
    """
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / ".gitignore"
    if not marker.exists():
        marker.write_text("*\n", encoding="utf-8")


def worktree_root(project_path: Path, task_id: str) -> Path:
    base = project_path / ".orchestrator" / "runtime" / "worktrees"
    ensure_ignored(base)
    return base / _sanitize(task_id)


def create_worktree(
    project_path: Path, task_id: str, subtask_id: str, *, base: str | None = None
) -> WorktreeHandle:
    """Cria worktree detached em .orchestrator/runtime/worktrees/<task>/<sub>.

    Fica DENTRO do projeto de propósito: o CliExecutor recusa cwd fora da raiz
    (assert_within_project), então worktree em %TEMP% não seria executável.
    """
    base_commit = base or git_head(project_path)
    if not base_commit:
        raise RuntimeError("worktree exige repositório git com HEAD")
    root = worktree_root(project_path, task_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / _sanitize(subtask_id)
    if path.exists():
        remove_worktree(project_path, path)
    result = run_git(
        project_path,
        "worktree",
        "add",
        "--detach",
        str(path),
        base_commit,
        timeout_s=WORKTREE_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add falhou ({result.returncode}): "
            f"{(result.stderr or '').strip()[:400]}"
        )
    return WorktreeHandle(subtask_id=subtask_id, path=path, base_commit=base_commit)


def collect_patch(handle: WorktreeHandle) -> str:
    """Diff da subtarefa contra o commit base, incluindo arquivos novos.

    `git add -A` aqui é seguro: a árvore é privada da subtarefa. Arquivos
    ignorados pelo .gitignore ficam de fora — artefato de build não deve
    atravessar a fusão.
    """
    staged = run_git(handle.path, "add", "-A", timeout_s=WORKTREE_TIMEOUT_S)
    if staged.returncode != 0:
        return ""
    diff = run_git(
        handle.path,
        "diff",
        "--cached",
        "--binary",
        handle.base_commit,
        timeout_s=WORKTREE_TIMEOUT_S,
    )
    if diff.returncode != 0:
        return ""
    return diff.stdout or ""


def dirty_patch(project_path: Path) -> str:
    """Diff do que a árvore real tem de NÃO COMMITADO, sem tocar no índice dela.

    0.4.74 — worktree nasce como checkout de HEAD, então um agente dentro dele
    não veria o trabalho não commitado da árvore real. Numa frota onde a árvore
    quase sempre tem trabalho em andamento, isso mudaria silenciosamente o que o
    agente enxerga: ele partiria de um estado que não existe mais.

    `git diff HEAD --binary` é somente leitura de propósito. Estagiar a árvore
    real (`git add -A`) para produzir o diff é exatamente o que causou o bug-077
    — levaria o trabalho não commitado do dono para o índice dele.

    Cobre arquivo rastreado modificado ou removido. Arquivo NÃO rastreado fica de
    fora (não está em `diff HEAD`) e é copiado por `untracked_files`.
    """
    diff = run_git(
        project_path, "diff", "HEAD", "--binary", timeout_s=WORKTREE_TIMEOUT_S
    )
    if diff.returncode != 0:
        return ""
    return diff.stdout or ""


# Estado do runtime, não do projeto: o banco SQLite vivo, os worktrees, os
# resultados e os backups. Semear isso copiaria o banco em uso para dentro do
# worktree — leitura possivelmente rasgada, e um `orchestrator` invocado ali
# resolveria a config para o banco errado. São as mesmas pastas que o CLAUDE.md
# manda não vasculhar, pelo mesmo motivo: são geradas.
SEED_SKIP_PREFIXES: tuple[str, ...] = (
    ".orchestrator/data/",
    ".orchestrator/runtime/",
    ".orchestrator/backups/",
)


def _seed_skips(rel: str) -> bool:
    normalizado = rel.replace("\\", "/")
    return any(normalizado.startswith(p) for p in SEED_SKIP_PREFIXES)


def untracked_files(project_path: Path) -> list[str]:
    """Arquivos novos ainda não rastreados, respeitando o .gitignore."""
    result = run_git(
        project_path,
        "ls-files",
        "--others",
        "--exclude-standard",
        timeout_s=WORKTREE_TIMEOUT_S,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def seed_worktree(project_path: Path, handle: WorktreeHandle) -> WorktreeHandle:
    """Deixa o worktree igual à árvore real e COMMITA isso ali dentro.

    O commit é o ponto do desenho: sem ele, o `collect_patch` no fim devolveria o
    trabalho não commitado do dono junto com o do agente, e a fusão tentaria
    reaplicar na árvore real mudanças que já estão nela — conflito garantido em
    toda task. Commitando a semente, `base_commit` passa a ser "o mundo como o
    agente o encontrou", e o patch de volta contém SÓ o delta do agente.

    O commit vive no worktree detached e nunca é publicado: some com o
    `worktree remove`. Devolve um handle novo com o base atualizado — em caso de
    falha, devolve o original (worktree em HEAD ainda é utilizável).
    """
    patch = dirty_patch(project_path)
    if patch.strip():
        patch_path = handle.path / ".orchestrator-seed.patch"
        patch_path.write_bytes(patch.encode("utf-8"))
        applied = run_git(
            handle.path,
            "apply",
            "--whitespace=nowarn",
            str(patch_path),
            timeout_s=WORKTREE_TIMEOUT_S,
        )
        patch_path.unlink(missing_ok=True)
        if applied.returncode != 0:
            return handle

    for rel in untracked_files(project_path):
        if _seed_skips(rel):
            continue
        origem = project_path / rel
        destino = handle.path / rel
        # O worktree mora DENTRO do projeto: sem isto ele se copiaria para
        # dentro de si mesmo a cada task.
        try:
            if origem.resolve() == destino.resolve() or handle.path in origem.parents:
                continue
        except OSError:
            continue
        if not origem.is_file():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(origem, destino)
        except OSError:
            continue  # arquivo em uso / link quebrado: seguir sem ele

    staged = run_git(handle.path, "add", "-A", timeout_s=WORKTREE_TIMEOUT_S)
    if staged.returncode != 0:
        return handle
    limpo = run_git(handle.path, "diff", "--cached", "--quiet")
    if limpo.returncode == 0:
        return handle  # árvore real estava limpa: HEAD já é a semente
    commit = run_git(
        handle.path,
        "-c",
        "user.name=orchestrator",
        "-c",
        "user.email=orchestrator@starfusion.local",
        "commit",
        "--no-verify",
        "--no-gpg-sign",
        "-m",
        "orchestrator: estado da arvore real ao iniciar a task",
        timeout_s=WORKTREE_TIMEOUT_S,
    )
    if commit.returncode != 0:
        return handle
    novo_base = git_head(handle.path)
    if not novo_base:
        return handle
    return WorktreeHandle(
        subtask_id=handle.subtask_id, path=handle.path, base_commit=novo_base
    )


def patch_files(patch: str) -> list[str]:
    """Paths tocados pelo patch (para detectar sobreposição entre subtarefas)."""
    out: list[str] = []
    for line in patch.splitlines():
        if not line.startswith("+++ "):
            continue
        path = line[4:].strip()
        if path == "/dev/null":
            continue
        if path.startswith("b/"):
            path = path[2:]
        if path:
            out.append(path)
    return sorted(dict.fromkeys(out))


def apply_patch(
    project_path: Path, patch: str, *, patch_path: Path
) -> tuple[bool, str]:
    """Aplica o patch na árvore real. Tudo-ou-nada: `--check` antes de escrever."""
    if not patch.strip():
        return True, ""
    ensure_ignored(patch_path.parent)
    # newline="" + escrita binária: git é rígido com o patch; CRLF injetado
    # pelo Windows quebra o "corrupt patch at line N".
    patch_path.write_bytes(patch.encode("utf-8"))
    check = run_git(
        project_path,
        "apply",
        "--check",
        "--whitespace=nowarn",
        str(patch_path),
        timeout_s=WORKTREE_TIMEOUT_S,
    )
    if check.returncode != 0:
        return False, (check.stderr or check.stdout or "git apply --check falhou")[:600]
    applied = run_git(
        project_path,
        "apply",
        "--whitespace=nowarn",
        str(patch_path),
        timeout_s=WORKTREE_TIMEOUT_S,
    )
    if applied.returncode != 0:
        return False, (applied.stderr or applied.stdout or "git apply falhou")[:600]
    return True, ""


def remove_worktree(project_path: Path, path: Path) -> None:
    """Remove o worktree; limpeza nunca derruba a task."""
    run_git(
        project_path,
        "worktree",
        "remove",
        "--force",
        str(path),
        timeout_s=WORKTREE_TIMEOUT_S,
    )
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    run_git(project_path, "worktree", "prune")


def cleanup_task_worktrees(project_path: Path, task_id: str) -> None:
    root = worktree_root(project_path, task_id)
    if not root.exists():
        run_git(project_path, "worktree", "prune")
        return
    for child in sorted(root.iterdir()):
        if child.is_dir():
            remove_worktree(project_path, child)
    shutil.rmtree(root, ignore_errors=True)
    run_git(project_path, "worktree", "prune")
