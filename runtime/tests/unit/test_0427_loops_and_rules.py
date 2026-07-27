"""0.4.27 — loops de execução + injeção de regras do projeto.

Loop: o pedido escolhe um roteiro nomeado (bug/mvp/landing/conteudo/saas) com
etapas e critérios próprios, em vez de terminar numa resposta.
Rules: as regras do projeto (.cursor/rules) passam a chegar ao executor.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.planning.analyzer import CriteriaBuilder, Planner, TaskAnalyzer
from orchestrator_runtime.planning.loops import LOOPS, detect_loop, get_loop
from orchestrator_runtime.rules.discovery import discover_rules, select_rules
from orchestrator_runtime.tasks.models import (
    CriterionKind,
    OrchestrationPlan,
    TaskRecord,
)


# --------------------------------------------------------------- loops

def test_detect_loop_por_pedido() -> None:
    assert detect_loop("Corrigir o bug do cálculo de prazo") == "bug"
    assert detect_loop("Criar um MVP do zero para agendamento") == "mvp"
    assert detect_loop("Auditar a landing page de vendas") == "landing"
    assert detect_loop("Escrever um post/carrossel sobre o produto") == "conteudo"
    assert detect_loop("Entregar a feature completa ponta a ponta") == "saas"


def test_sem_match_nao_impoe_loop() -> None:
    assert detect_loop("Renomear a variável x para y") is None
    assert detect_loop("") is None


def test_prefixo_explicito_vence_heuristica() -> None:
    # texto é de conteúdo, mas o usuário pediu o loop de bug
    assert detect_loop("/loop-bug escrever o post sobre o artigo") == "bug"
    assert detect_loop("/bug ajustar a legenda do carrossel") == "bug"


def test_bug_vence_mvp_em_empate() -> None:
    assert detect_loop("corrigir bug no MVP do zero") == "bug"


def test_intencao_de_codigo_nao_vira_auditoria_de_landing() -> None:
    assert detect_loop("implementar o formulário da landing page") != "landing"


def test_criterios_vem_do_loop() -> None:
    analysis = TaskAnalyzer().analyze("Corrigir o bug do cálculo de prazo")
    assert analysis.loop == "bug"

    criteria = CriteriaBuilder().build("Corrigir o bug do cálculo de prazo", analysis)
    ids = [c.id for c in criteria]
    assert ids == ["AC-001", "AC-002", "AC-003"]
    assert any("reproduz" in c.description.lower() for c in criteria)
    assert any(c.kind == CriterionKind.TESTS_PASS for c in criteria)


def test_acs_declarados_vencem_o_loop() -> None:
    prompt = "Corrigir o bug X\n- AC-001: entregar o relatorio da investigacao\n"
    analysis = TaskAnalyzer().analyze(prompt)
    criteria = CriteriaBuilder().build(prompt, analysis)

    assert len(criteria) == 1
    assert "relatorio da investigacao" in criteria[0].description


def test_plano_carrega_o_loop(tmp_path: Path) -> None:
    analysis = TaskAnalyzer().analyze("Corrigir o bug do cálculo")
    task = TaskRecord(prompt="Corrigir o bug do cálculo", project_path=str(tmp_path))
    roles = OrchestrationPlan(
        strategy="execute_review_repair",
        planner="claude",
        executor="codex",
        validator="claude",
    )
    plan = Planner().plan(task, analysis, roles)

    assert plan["loop"] == "bug"
    assert plan["loop_stages"], "etapas do loop precisam ir para o plano"
    assert "reproduzir" in plan["loop_stages"][0].lower()


def test_briefing_lista_etapas_em_ordem() -> None:
    briefing = get_loop("bug").briefing()
    assert "/bug" in briefing
    assert "1. Reproduzir" in briefing
    assert briefing.index("Reproduzir") < briefing.index("Corrigir")


def test_todos_os_loops_bem_formados() -> None:
    for loop_id, spec in LOOPS.items():
        assert spec.id == loop_id
        assert spec.stages, f"{loop_id} sem etapas"
        assert spec.criteria, f"{loop_id} sem criterios"
        assert spec.done_when, f"{loop_id} sem condicao de conclusao"
        assert len(spec.to_criteria()) == len(spec.criteria)


# --------------------------------------------------------------- rules

def _mk_rule(base: Path, name: str, description: str, *, always: bool = False,
             globs: str = "") -> None:
    d = base / ".cursor" / "rules"
    d.mkdir(parents=True, exist_ok=True)
    fm = ["---", f"description: {description}"]
    if globs:
        fm.append(f"globs: {globs}")
    fm.append(f"alwaysApply: {'true' if always else 'false'}")
    fm.append("---")
    (d / f"{name}.mdc").write_text("\n".join(fm) + "\ncorpo da regra\n", encoding="utf-8")


def test_discover_rules_le_frontmatter(tmp_path: Path) -> None:
    _mk_rule(tmp_path, "backend_dotnet", "Padroes backend .NET, DDD, CQRS",
             globs='["**/*.cs"]')
    _mk_rule(tmp_path, "git_workflow", "Fluxo de git do time", always=True)

    rules = {r.rule_id: r for r in discover_rules(tmp_path)}
    assert set(rules) == {"backend_dotnet", "git_workflow"}
    assert rules["git_workflow"].always_apply is True
    assert rules["backend_dotnet"].globs == ("**/*.cs",)


def test_select_rules_prioriza_relevancia_e_always(tmp_path: Path) -> None:
    _mk_rule(tmp_path, "backend_dotnet", "Padroes backend dotnet com CQRS e EF Core")
    _mk_rule(tmp_path, "frontend_angular", "Padroes frontend Angular e componentes")
    _mk_rule(tmp_path, "git_workflow", "Fluxo de git do time", always=True)

    selected = select_rules(tmp_path, "Ajustar o componente Angular do backoffice")
    ids = [r.rule_id for r in selected]

    assert "git_workflow" in ids, "alwaysApply entra sempre"
    assert "frontend_angular" in ids, "regra relevante ao pedido entra"
    assert ids.index("git_workflow") < ids.index("frontend_angular")
    assert "backend_dotnet" not in ids, "regra irrelevante fica de fora"


def test_select_rules_sem_regras_nao_quebra(tmp_path: Path) -> None:
    assert select_rules(tmp_path, "qualquer coisa") == []
