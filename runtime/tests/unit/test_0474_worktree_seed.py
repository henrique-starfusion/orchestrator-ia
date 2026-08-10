"""0.4.74 — worktree semeado: o agente ve o MESMO estado da arvore real.

Worktree nasce como checkout de HEAD. Numa frota onde a arvore quase sempre tem
trabalho em andamento, rodar o agente ali sem semear mudaria silenciosamente o
que ele enxerga: ele partiria de um estado que nao existe mais.

E o commit da semente nao e detalhe. Sem ele, `collect_patch` no fim devolveria o
trabalho nao commitado do dono junto com o do agente, e a fusao tentaria
reaplicar na arvore real o que ja esta nela — conflito garantido em TODA task.
Commitando a semente, `base_commit` passa a ser "o mundo como o agente o
encontrou" e o patch de volta contem so o delta do agente.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from orchestrator_runtime.execution.worktrees import (
    apply_patch,
    collect_patch,
    create_worktree,
    dirty_patch,
    git_head,
    patch_files,
    seed_worktree,
    untracked_files,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


def _repo(project: Path) -> None:
    _git(project, "init")
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "Test")
    (project / "base.txt").write_text("v1\n", encoding="utf-8")
    _git(project, "add", "base.txt")
    _git(project, "commit", "-m", "base")


# --------------------------------------------------------------------------
# as duas leituras da arvore real
# --------------------------------------------------------------------------


def test_dirty_patch_ve_modificacao_nao_commitada(project: Path) -> None:
    _repo(project)
    (project / "base.txt").write_text("v2\n", encoding="utf-8")

    assert "base.txt" in patch_files(dirty_patch(project))


def test_dirty_patch_de_arvore_limpa_e_vazio(project: Path) -> None:
    _repo(project)

    assert dirty_patch(project).strip() == ""


def test_untracked_respeita_gitignore(project: Path) -> None:
    _repo(project)
    (project / ".gitignore").write_text("ignorado.txt\n", encoding="utf-8")
    (project / "ignorado.txt").write_text("x\n", encoding="utf-8")
    (project / "visivel.py").write_text("y\n", encoding="utf-8")

    achados = untracked_files(project)

    assert "visivel.py" in achados
    assert "ignorado.txt" not in achados


# --------------------------------------------------------------------------
# semear
# --------------------------------------------------------------------------


def test_seed_leva_modificacao_nao_commitada(project: Path) -> None:
    _repo(project)
    (project / "base.txt").write_text("v2-nao-commitado\n", encoding="utf-8")

    handle = seed_worktree(project, create_worktree(project, "t1", "main"))

    assert (handle.path / "base.txt").read_text(encoding="utf-8") == (
        "v2-nao-commitado\n"
    )


def test_seed_leva_arquivo_novo_nao_rastreado(project: Path) -> None:
    """`git diff HEAD` nao ve arquivo novo; ele e copiado a parte."""
    _repo(project)
    (project / "novo.py").write_text("print(1)\n", encoding="utf-8")

    handle = seed_worktree(project, create_worktree(project, "t2", "main"))

    assert (handle.path / "novo.py").read_text(encoding="utf-8") == "print(1)\n"


def test_seed_leva_remocao_nao_commitada(project: Path) -> None:
    _repo(project)
    (project / "base.txt").unlink()

    handle = seed_worktree(project, create_worktree(project, "t2b", "main"))

    assert not (handle.path / "base.txt").exists()


def test_seed_nao_estagia_a_arvore_real(project: Path) -> None:
    """bug-077: estagiar a arvore real levaria o trabalho do dono para o indice."""
    _repo(project)
    (project / "base.txt").write_text("v2\n", encoding="utf-8")
    (project / "novo.py").write_text("x\n", encoding="utf-8")

    seed_worktree(project, create_worktree(project, "t3", "main"))

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(project),
        capture_output=True,
        text=True,
    )
    assert staged.stdout.strip() == "", "indice da arvore real foi tocado"


def test_seed_avanca_o_base_commit(project: Path) -> None:
    _repo(project)
    (project / "base.txt").write_text("v2\n", encoding="utf-8")
    original = create_worktree(project, "t3b", "main")

    handle = seed_worktree(project, original)

    assert handle.base_commit != original.base_commit


def test_seed_com_arvore_limpa_mantem_head(tmp_path: Path) -> None:
    """Nada sujo, nada a commitar: a semente e o proprio HEAD."""
    projeto = tmp_path / "repo"
    projeto.mkdir()
    _repo(projeto)

    handle = seed_worktree(projeto, create_worktree(projeto, "t6", "main"))

    assert handle.base_commit == git_head(projeto)


def test_seed_nao_copia_o_banco_vivo_nem_os_worktrees(project: Path) -> None:
    """`.orchestrator/data` e `.orchestrator/runtime` sao estado do RUNTIME.

    Copiar o SQLite em uso para dentro do worktree daria leitura possivelmente
    rasgada, e um `orchestrator` invocado ali resolveria a config para o banco
    errado. Os worktrees moram sob `runtime/`, entao sem isto cada task copiaria
    os worktrees das outras.
    """
    _repo(project)
    banco = project / ".orchestrator" / "data" / "orchestrator.db"
    banco.parent.mkdir(parents=True, exist_ok=True)
    banco.write_bytes(b"SQLite format 3\x00fingido")
    config = project / ".orchestrator" / "config" / "policies.json"

    handle = seed_worktree(project, create_worktree(project, "t6b", "main"))

    assert not (handle.path / ".orchestrator" / "data" / "orchestrator.db").exists()
    assert not (handle.path / ".orchestrator" / "runtime").exists()
    # config do projeto continua indo: ela e do projeto, nao estado do runtime
    assert config.is_file()
    assert (handle.path / ".orchestrator" / "config" / "policies.json").is_file()


# --------------------------------------------------------------------------
# o ciclo fechado: coletar no worktree, fundir na arvore real suja
# --------------------------------------------------------------------------


def test_patch_de_volta_contem_so_o_delta_do_agente(project: Path) -> None:
    _repo(project)
    (project / "base.txt").write_text("mexido-pelo-dono\n", encoding="utf-8")
    handle = seed_worktree(project, create_worktree(project, "t4", "main"))

    (handle.path / "do_agente.py").write_text("ok\n", encoding="utf-8")

    assert patch_files(collect_patch(handle)) == ["do_agente.py"], (
        "o patch levou trabalho do dono junto com o do agente"
    )


def test_fusao_preserva_o_trabalho_do_dono(project: Path) -> None:
    _repo(project)
    (project / "base.txt").write_text("mexido-pelo-dono\n", encoding="utf-8")
    handle = seed_worktree(project, create_worktree(project, "t5", "main"))
    (handle.path / "do_agente.py").write_text("ok\n", encoding="utf-8")

    ok, err = apply_patch(
        project, collect_patch(handle), patch_path=project / ".tmp" / "t5.patch"
    )

    assert ok, err
    assert (project / "do_agente.py").read_text(encoding="utf-8") == "ok\n"
    assert (project / "base.txt").read_text(encoding="utf-8") == "mexido-pelo-dono\n"


def test_agente_editando_arquivo_que_o_dono_mexeu_tambem(project: Path) -> None:
    """O agente altera o MESMO arquivo que o dono deixou sujo.

    Como a semente e a base, o patch e o delta sobre o estado que o agente viu —
    entao a fusao aplica limpa em cima do trabalho do dono.
    """
    _repo(project)
    (project / "base.txt").write_text("linha-do-dono\n", encoding="utf-8")
    handle = seed_worktree(project, create_worktree(project, "t7", "main"))
    (handle.path / "base.txt").write_text(
        "linha-do-dono\nlinha-do-agente\n", encoding="utf-8"
    )

    ok, err = apply_patch(
        project, collect_patch(handle), patch_path=project / ".tmp" / "t7.patch"
    )

    assert ok, err
    assert (project / "base.txt").read_text(encoding="utf-8") == (
        "linha-do-dono\nlinha-do-agente\n"
    )


def test_conflito_nao_suja_a_arvore_real(project: Path) -> None:
    """Politica escolhida: conflito volta pro corrector, arvore real intacta.

    O agente parte da semente; DEPOIS o dono muda a mesma linha na arvore real.
    O patch nao encaixa mais e `--check` recusa antes de escrever byte nenhum.
    """
    _repo(project)
    (project / "base.txt").write_text("estado-que-o-agente-viu\n", encoding="utf-8")
    handle = seed_worktree(project, create_worktree(project, "t8", "main"))
    (handle.path / "base.txt").write_text("versao-do-agente\n", encoding="utf-8")
    # o dono (ou outra task) muda a mesma linha enquanto o agente trabalhava
    (project / "base.txt").write_text("mudou-por-fora\n", encoding="utf-8")

    ok, err = apply_patch(
        project, collect_patch(handle), patch_path=project / ".tmp" / "t8.patch"
    )

    assert ok is False
    assert err
    assert (project / "base.txt").read_text(encoding="utf-8") == "mudou-por-fora\n", (
        "arvore real tinha que ficar intacta no conflito"
    )
