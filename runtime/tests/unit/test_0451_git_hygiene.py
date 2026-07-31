"""0.4.51 — higiene git em árvore compartilhada (bug-077).

printbee, 2026-07-30: SEIS quase-arrastões num dia, evitados só por
disciplina do agente — um encontrou docker-compose.yml com mudança não
commitada de OUTRO agente e montou patch isolado do próprio trecho (1
arquivo, 2 linhas) em vez de `git add -A`. Segurança não pode depender de
disciplina: o executor/corrector agora recebe sempre o bloco de higiene
(stage explícito; trabalho alheio intacto), e o guard hook (Write|Edit|
MultiEdit|Bash) bloqueia uma vez os padrões perigosos — verificado manual:
`git add -A` exit 2, repetição exit 0, `git add src/x.py` exit 0,
`git clean -fd` exit 2.
"""

from __future__ import annotations

from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService


def test_prompt_do_executor_traz_higiene_git(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("implemente e commite X 0451")
    prompt = service._build_executor_prompt(task, {}, [], test_results=None)
    assert "Higiene git" in prompt
    assert "git add -A" in prompt
    assert "git add <path>" in prompt
    assert "trabalho alheio fica intacto" in prompt


def test_blocos_proibidos_cobrem_arrastao_e_destruicao(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("qualquer 0451")
    prompt = service._build_executor_prompt(task, {}, [], test_results=None)
    for forbidden in ("git commit -a", "git stash", "git clean",
                      "git reset --hard", "checkout/restore"):
        assert forbidden in prompt, forbidden
