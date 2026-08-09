"""0.4.68 — enfraquecimento de teste deixa de passar em branco.

O executor escreve o codigo E os testes, e o gate so verifica se a suite fica
verde. Nada impedia baixar uma assercao, marcar skip ou apagar um caso para
passar — e o resultado saia COMPLETED score=1.0, igual a trabalho honesto.

Heuristica reimplementada a partir do `fable-judge` (MIT): "um teste alterado e
culpado ate a justificativa remontar a uma spec". Severidade e NAO-BLOQUEANTE de
proposito: refator legitimo remove assercao, e esta frota ja pagou caro por
heuristica de texto confiante demais (bug-097).
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.validation.test_integrity import (
    analyze_diff,
    is_test_path,
    summarize,
)


def _diff(path: str, corpo: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{corpo}"


# --------------------------------------------------------------------------
# reconhecimento de arquivo de teste
# --------------------------------------------------------------------------


def test_reconhece_caminhos_de_teste_das_stacks_da_frota() -> None:
    for p in (
        "runtime/tests/unit/test_x.py",
        "src/backend/tests/UnitTest/PayrollTests.cs",
        "src/frontend/app/foo.spec.ts",
        "web/__tests__/bar.test.js",
        "pkg/handler_test.go",
    ):
        assert is_test_path(p), p


def test_codigo_de_producao_nao_e_teste() -> None:
    for p in ("src/app/service.py", "src/backend/Payroll.cs", "web/app/main.ts"):
        assert not is_test_path(p), p


# --------------------------------------------------------------------------
# sinais de enfraquecimento
# --------------------------------------------------------------------------


def test_assercao_removida_e_sinalizada() -> None:
    diff = _diff(
        "tests/test_calc.py",
        "-    assert total == 300.00\n+    total = calc()\n",
    )
    achados = analyze_diff(diff)
    assert [a.kind for a in achados] == ["assertions_removed"]
    assert "tests/test_calc.py" in achados[0].path


def test_teste_desligado_por_skip_e_sinalizado() -> None:
    diff = _diff(
        "tests/test_calc.py",
        "+@pytest.mark.skip(reason='flaky')\n def test_total():\n",
    )
    kinds = [a.kind for a in analyze_diff(diff)]
    assert "tests_skipped" in kinds


def test_skip_do_dotnet_e_do_jest_tambem_contam() -> None:
    dotnet = _diff("tests/PayrollTests.cs", "+    [Fact(Skip = \"quebrado\")]\n")
    jest = _diff("web/__tests__/a.test.js", "+  it.skip('soma', () => {\n")
    assert "tests_skipped" in [a.kind for a in analyze_diff(dotnet)]
    assert "tests_skipped" in [a.kind for a in analyze_diff(jest)]


def test_caso_de_teste_apagado_e_sinalizado() -> None:
    diff = _diff(
        "tests/test_calc.py",
        "-def test_desconto_pix():\n-    assert desconto(100) == 5\n",
    )
    kinds = [a.kind for a in analyze_diff(diff)]
    assert "tests_deleted" in kinds
    assert "assertions_removed" in kinds


# --------------------------------------------------------------------------
# o que NAO pode virar suspeita (falso-positivo custa caro — bug-097)
# --------------------------------------------------------------------------


def test_adicionar_teste_nao_e_suspeito() -> None:
    diff = _diff(
        "tests/test_calc.py",
        "+def test_novo():\n+    assert calc() == 42\n+    assert calc() > 0\n",
    )
    assert analyze_diff(diff) == []


def test_trocar_assercao_por_assercao_nao_e_suspeito() -> None:
    """Refator legitimo: uma sai, uma entra."""
    diff = _diff(
        "tests/test_calc.py",
        "-    assert total == 300\n+    assert total == Decimal('300.00')\n",
    )
    assert analyze_diff(diff) == []


def test_mudanca_em_codigo_de_producao_e_ignorada() -> None:
    """So arquivo de TESTE interessa; apagar assercao em prod nao e o alvo."""
    diff = _diff(
        "src/app/calc.py",
        "-    assert entrada > 0\n+    pass\n",
    )
    assert analyze_diff(diff) == []


def test_diff_vazio_nao_inventa_achado() -> None:
    assert analyze_diff("") == []
    assert analyze_diff("diff --git a/x b/x\n") == []


# --------------------------------------------------------------------------
# integracao com o prompt do validador
# --------------------------------------------------------------------------


def test_resumo_vazio_quando_nao_ha_suspeita() -> None:
    assert summarize([]) == ""


def test_resumo_manda_o_validador_justificar() -> None:
    achados = analyze_diff(_diff("tests/t.py", "-    assert a == 1\n"))
    texto = summarize(achados)
    assert "CULPADO" in texto
    assert "blocking" in texto
    assert "tests/t.py" in texto


def test_achado_vira_issue_nao_bloqueante(project: Path) -> None:
    achados = analyze_diff(_diff("tests/t.py", "-    assert a == 1\n"))
    issue = achados[0].as_issue("VAL-TI01")
    assert issue["severity"] == "non_blocking"
    assert issue["kind"] == "test_integrity"


def test_servico_ignora_projeto_sem_arquivo_de_teste_alterado(project: Path) -> None:
    """Sem arquivo de teste no diff, nem chama o git."""
    from orchestrator_runtime.tasks.service import build_service

    svc = build_service(project, fake_agents=True)
    assert svc._test_integrity_findings(["src/app/main.py", "README.md"]) == []
