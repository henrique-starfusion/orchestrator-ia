"""0.4.61 — worktree por subtarefa: isolamento e fusão por patch."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orchestrator_runtime.execution.worktrees import (
    apply_patch,
    cleanup_task_worktrees,
    collect_patch,
    create_worktree,
    git_head,
    patch_files,
    worktrees_available,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True, text=True
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / ".orchestrator").mkdir(parents=True)
    _git(project.parent, "init", "proj")
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "test")
    (project / "app.py").write_text("print('base')\n", encoding="utf-8")
    (project / "README.md").write_text("# base\n", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "base")
    return project


def test_repo_sem_commit_nao_suporta_worktree(tmp_path: Path) -> None:
    empty = tmp_path / "vazio"
    empty.mkdir()
    _git(tmp_path, "init", "vazio")
    assert worktrees_available(empty) is False
    assert git_head(empty) is None


def test_pasta_sem_git_nao_suporta(tmp_path: Path) -> None:
    plain = tmp_path / "semgit"
    plain.mkdir()
    assert worktrees_available(plain) is False


def test_worktree_isola_escrita(repo: Path) -> None:
    handle = create_worktree(repo, "task1", "s1")
    try:
        (handle.path / "app.py").write_text("print('subtarefa')\n", encoding="utf-8")
        # A árvore real não enxerga nada: isso é o ponto do isolamento.
        assert (repo / "app.py").read_text(encoding="utf-8") == "print('base')\n"
    finally:
        cleanup_task_worktrees(repo, "task1")


def test_patch_carrega_arquivo_novo_e_editado(repo: Path) -> None:
    handle = create_worktree(repo, "task2", "s1")
    try:
        (handle.path / "app.py").write_text("print('editado')\n", encoding="utf-8")
        (handle.path / "novo.py").write_text("x = 1\n", encoding="utf-8")
        patch = collect_patch(handle)
    finally:
        cleanup_task_worktrees(repo, "task2")

    assert patch.strip()
    assert set(patch_files(patch)) == {"app.py", "novo.py"}


def test_patch_vazio_quando_nada_muda(repo: Path) -> None:
    handle = create_worktree(repo, "task3", "s1")
    try:
        assert collect_patch(handle).strip() == ""
    finally:
        cleanup_task_worktrees(repo, "task3")


def test_fusao_de_duas_subtarefas_disjuntas(repo: Path) -> None:
    a = create_worktree(repo, "task4", "s1")
    b = create_worktree(repo, "task4", "s2")
    try:
        (a.path / "app.py").write_text("print('de A')\n", encoding="utf-8")
        (b.path / "extra.py").write_text("y = 2\n", encoding="utf-8")
        patch_a = collect_patch(a)
        patch_b = collect_patch(b)
    finally:
        cleanup_task_worktrees(repo, "task4")

    pdir = repo / ".orchestrator" / "runtime" / "patches" / "task4"
    ok_a, err_a = apply_patch(repo, patch_a, patch_path=pdir / "s1.patch")
    ok_b, err_b = apply_patch(repo, patch_b, patch_path=pdir / "s2.patch")

    assert (ok_a, err_a) == (True, "")
    assert (ok_b, err_b) == (True, "")
    assert (repo / "app.py").read_text(encoding="utf-8") == "print('de A')\n"
    assert (repo / "extra.py").read_text(encoding="utf-8") == "y = 2\n"


def test_conflito_nao_suja_a_arvore(repo: Path) -> None:
    """Patch que não aplica é reportado — e a árvore real fica intacta."""
    a = create_worktree(repo, "task5", "s1")
    b = create_worktree(repo, "task5", "s2")
    try:
        (a.path / "app.py").write_text("print('versao A')\n", encoding="utf-8")
        (b.path / "app.py").write_text("print('versao B')\n", encoding="utf-8")
        patch_a = collect_patch(a)
        patch_b = collect_patch(b)
    finally:
        cleanup_task_worktrees(repo, "task5")

    pdir = repo / ".orchestrator" / "runtime" / "patches" / "task5"
    ok_a, _ = apply_patch(repo, patch_a, patch_path=pdir / "s1.patch")
    ok_b, err_b = apply_patch(repo, patch_b, patch_path=pdir / "s2.patch")

    assert ok_a is True
    assert ok_b is False
    assert err_b
    conteudo = (repo / "app.py").read_text(encoding="utf-8")
    assert conteudo == "print('versao A')\n"
    assert "<<<<<<<" not in conteudo  # nada de merge pela metade


def test_patch_vazio_e_no_op(repo: Path) -> None:
    pdir = repo / ".orchestrator" / "runtime" / "patches" / "task6"
    assert apply_patch(repo, "", patch_path=pdir / "s1.patch") == (True, "")
    assert apply_patch(repo, "   \n", patch_path=pdir / "s2.patch") == (True, "")


def test_worktree_nao_polui_git_status_do_projeto(repo: Path) -> None:
    """Projeto que versiona .orchestrator/ não pode ver a árvore duplicada."""
    handle = create_worktree(repo, "task9", "s1")
    try:
        (handle.path / "app.py").write_text("print('x')\n", encoding="utf-8")
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "worktrees" not in status
        assert "app.py" not in status  # o do worktree, não o da raiz
    finally:
        cleanup_task_worktrees(repo, "task9")


def test_patches_tambem_ficam_ignorados(repo: Path) -> None:
    handle = create_worktree(repo, "task10", "s1")
    try:
        (handle.path / "novo.md") .write_text("x\n", encoding="utf-8")
        patch = collect_patch(handle)
    finally:
        cleanup_task_worktrees(repo, "task10")
    pdir = repo / ".orchestrator" / "runtime" / "patches" / "task10"
    apply_patch(repo, patch, patch_path=pdir / "s1.patch")

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "patches" not in status
    assert "novo.md" in status  # o entregável entra; o patch, não


def test_cleanup_remove_tudo(repo: Path) -> None:
    handle = create_worktree(repo, "task7", "s1")
    assert handle.path.is_dir()
    cleanup_task_worktrees(repo, "task7")
    assert not handle.path.exists()
    listed = subprocess.run(
        ["git", "worktree", "list"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "task7" not in listed.stdout


def test_recriar_mesmo_id_nao_quebra(repo: Path) -> None:
    first = create_worktree(repo, "task8", "s1")
    (first.path / "app.py").write_text("print('primeira')\n", encoding="utf-8")
    second = create_worktree(repo, "task8", "s1")
    try:
        assert second.path == first.path
        # Recriado a partir do base: o rascunho anterior não vaza.
        assert (second.path / "app.py").read_text(encoding="utf-8") == "print('base')\n"
    finally:
        cleanup_task_worktrees(repo, "task8")
