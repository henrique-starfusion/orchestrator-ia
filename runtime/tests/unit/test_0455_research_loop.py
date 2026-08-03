"""0.4.55 — /loop-research agent-agnóstico + skill karpathy.

Portado do demo research-agent da Anthropic (Claude Agent SDK): padrão
Lead→Researchers→Analyst→Writer com handoff por arquivos, adaptado para UM
executor sequencial de QUALQUER CLI — o executor usa a busca web do próprio
agente (WebSearch/web.run/google_search), grava notas com URLs, extrai dados
e gráficos, redige relatório com citações e lacunas marcadas. A honestidade
("não encontrado" em vez de preencher com conhecimento interno) é etapa
obrigatória, não sugestão.
"""

from __future__ import annotations

import json

from orchestrator_runtime.planning.loops import LOOPS, detect_loop, get_loop


def test_loop_research_existe_completo() -> None:
    spec = get_loop("research")
    assert spec is not None
    assert len(spec.stages) >= 5
    assert len(spec.criteria) >= 4
    joined = " ".join(spec.stages)
    for marker in ("busca web", "notes/", "charts/", "reports/", "REVISÃO DE HONESTIDADE"):
        assert marker in joined, marker
    # agent-agnóstico: cita as ferramentas de cada CLI e a saída honesta sem busca
    assert "google_search" in joined or "WebSearch" in joined
    assert "nunca simule pesquisa" in joined


def test_criterios_cobrem_contrato_de_artefatos() -> None:
    spec = LOOPS["research"]
    descs = " ".join(d for d, _ in spec.criteria)
    for marker in ("00-plano.md", "notes/", "reports/", "charts/", "lacunas"):
        assert marker in descs, marker


def test_detecta_research_por_keywords() -> None:
    assert detect_loop("Pesquisa de mercado sobre tendências de IA em 2026") == "research"
    assert detect_loop("/loop-research impacto do PIX no varejo") == "research"
    assert detect_loop("research the current state of quantum error correction") == "research"


def test_nao_regressao_bug_e_curto() -> None:
    # bug continua vencendo pedido de correção
    assert detect_loop("corrigir erro no cálculo de prazo de produção") == "bug"
    # prompt longo com 1 hit incidental de research não liga o loop
    texto_longo = "Implementar exportação CSV no módulo de relatórios. " + (
        "Contexto adicional sobre a feature e seus detalhes técnicos. " * 8
    ) + "Mencionei a palavra pesquisa uma vez só."
    assert detect_loop(texto_longo) != "research"


def test_skill_karpathy_registrada() -> None:
    import pathlib

    registry = (
        pathlib.Path(__file__).resolve().parents[3]
        / "package"
        / "template"
        / ".orchestrator"
        / "skills"
        / "registry.json"
    )
    data = json.loads(registry.read_text(encoding="utf-8-sig"))
    ids = [s["id"] for s in data["skills"]]
    assert "karpathy-guidelines" in ids
    skill = registry.parent / "karpathy-guidelines" / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    for principio in ("Pense antes de codar", "Simplicidade primeiro",
                      "Mudanças cirúrgicas", "dirigida por objetivo"):
        assert principio in text, principio
