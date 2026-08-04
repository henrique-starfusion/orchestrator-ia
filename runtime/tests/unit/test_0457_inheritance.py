"""0.4.57 — herança de skills/rules/agents do modelo no spawn (bug-081).

O agente chamado pelo orquestrador (executor/corrector) deve herdar skills,
rules e agents tanto do .orchestrator quanto do PRÓPRIO runtime de IA que
ele é (claude/codex/kimi/opencode): rules em .codex/.claude/.kimi-code,
skills em .kimi-code/.gemini, e as personas de .claude/.codex/.kimi-code/
.opencode agents como guia de escopo (nunca delegação).
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.config import load_config
from orchestrator_runtime.rules.discovery import discover_rules
from orchestrator_runtime.skills.discovery import discover_skills
from orchestrator_runtime.tasks.service import TaskService


def test_rules_inclui_codex_e_claude(tmp_path: Path) -> None:
    # nomes diferentes por dir: a deduplicação é por nome de arquivo
    casos = {
        ".codex/rules": "regra-codex.md",
        ".claude/rules": "regra-claude.md",
        ".kimi-code/rules": "regra-kimi.md",
    }
    for rel, fname in casos.items():
        d = tmp_path / rel
        d.mkdir(parents=True)
        (d / fname).write_text(
            "---\ndescription: regra de teste bug-081\nalwaysApply: true\n---\nUse o padrão X do time.\n",
            encoding="utf-8",
        )
    rules = discover_rules(tmp_path)
    assert len(rules) >= 3, f"rules de outros runtimes ignoradas: {rules}"


def test_skills_inclui_kimi_code_e_gemini(tmp_path: Path) -> None:
    for rel in (".kimi-code/skills/minha-skill", ".gemini/skills/outra-skill"):
        d = tmp_path / rel
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\ndescription: skill de teste bug-081\n---\n# Skill X\n",
            encoding="utf-8",
        )
    skills = discover_skills(tmp_path, include_user_global=False)
    ids = [s.skill_id for s in skills]
    assert "minha-skill" in ids
    assert "outra-skill" in ids


def test_prompt_executor_lista_agents_do_projeto(project) -> None:
    agents_dir = project / ".codex" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "backend_developer.toml").write_text(
        'name = "backend_developer"\n', encoding="utf-8"
    )
    claude_dir = project / ".claude" / "agents"
    claude_dir.mkdir(parents=True)
    (claude_dir / "orquestrador.md").write_text("# x\n", encoding="utf-8")

    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("qualquer 0457")
    prompt = service._build_executor_prompt(task, {}, [], test_results=None)
    assert "Agentes definidos no projeto" in prompt
    assert ".codex/agents/backend_developer.toml" in prompt
    assert ".claude/agents/orquestrador.md" in prompt
    assert "NÃO delege" in prompt


def test_sem_agents_sem_bloco(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    assert service._agents_block() == ""
