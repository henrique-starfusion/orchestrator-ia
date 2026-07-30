"""0.4.46 — evidência de UI no loop-bug (bug-069).

Task 8193684389b1 (printbee): "/loop-bug BUG CONFIRMADO no navegador" —
defeito de renderização. Nem executor nem validador CLI abrem browser, e o
critério "Defeito reproduzido com evidência registrada" foi lido como
exigência de reprodução visual: validador reprovou 2x com a MESMA issue e o
same_issue_repeat_limit encerrou — task impossível por definição, não por
mérito. O template do loop-bug agora escopa o que conta como evidência
quando o defeito é de UI/renderização: teste que falha, DOM/snapshot do
HTML gerado ou análise estática do código de render.
"""

from __future__ import annotations

from orchestrator_runtime.planning.loops import LOOPS


def test_loop_bug_escopa_evidencia_de_ui() -> None:
    bug = LOOPS["bug"]
    stage1 = bug.stages[0]
    assert "UI/renderização" in stage1
    assert "não abrem navegador" in stage1
    assert "análise estática" in stage1 or "DOM" in stage1


def test_criterio_de_evidencia_do_loop_bug_aceita_canal_cli() -> None:
    bug = LOOPS["bug"]
    evid_texts = [desc for desc, _kind in bug.criteria if "evidência" in desc]
    assert evid_texts, "loop-bug perdeu o critério de evidência"
    texto = evid_texts[0]
    assert "DOM" in texto or "análise estática" in texto
    assert "não exigir screenshot" in texto
