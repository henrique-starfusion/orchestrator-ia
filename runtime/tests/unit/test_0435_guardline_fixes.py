"""0.4.35 — correções extraídas da auditoria GuardLine.BR (bug-045/046/047).

bug-045: detect_loop casava substring sem fronteira de palavra ("erro" dentro
    de "errors", "mvp" em "O MVP já existe") e um único hit incidental num
    prompt de 1500+ chars sequestrava os critérios da task inteira.
bug-046: critérios escritos pelo usuário como "Critérios: a; b; c" eram
    ignorados (só o formato AC-001: era reconhecido) e o template do loop
    vencia os critérios reais — tasks nasciam com ACs inatendíveis.
bug-047: changed_files_since não enxergava repos git aninhados (GuardLine.BR
    contém ~40 repos filhos) → changed=[] sempre → workspace_changes nunca
    passava, trabalho real virava AGENT-TIMEOUT-NO-OUTPUT.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orchestrator_runtime.execution.git_workspace import (
    capture_baseline,
    changed_files_since,
)
from orchestrator_runtime.planning.analyzer import (
    CriteriaBuilder,
    TaskAnalyzer,
    parse_criteria_section,
)
from orchestrator_runtime.planning.loops import detect_loop
from orchestrator_runtime.tasks.models import CriterionKind


# ------------------------------------------------------------------ bug-045

PROMPT_ERRORS_EN = (
    "travelex-api: fazer a bridge devolver os errors campo a campo do upstream "
    "SOCC: hoje FromProblemDetails em internal/errors/envelope.go descarta o "
    "array errors[] do problem+json; estender ErrorResponse com campo "
    "details/errors (path, code, message) preservando request_id e mapear em "
    "FromProblemDetails garantindo que os handlers propaguem os detalhes."
)


def test_erro_nao_casa_dentro_de_errors_ingles() -> None:
    # "erro" aparecia como substring de "errors" e ligava o loop de bug.
    assert detect_loop(PROMPT_ERRORS_EN) is None


def test_mencao_a_mvp_existente_nao_liga_loop_mvp() -> None:
    prompt = (
        "Concluir TODA a implementação Quod RUFRA no onp-api (fases 2 e 3). "
        "O MVP já existe: internal/provider/quod, CapFraudScreening, POST "
        "/api/v1/fraud/screen, wiring registry/env/orchestrator e docs. "
        "Fazer agora: identity binding no FraudService espelhando KYCService, "
        "consumo no pipeline de decisão com mapeamento score para blocking, "
        "persistência de evidência em provider_results, feature flag via env "
        "e testes unitários httptest para os fluxos novos do adapter Quod."
    )
    # 1 hit incidental ("mvp") num prompt longo não define o roteiro da task.
    assert detect_loop(prompt) is None


def test_clausula_condicional_nao_liga_loop_de_bug() -> None:
    prompt = (
        "travelex-api: publicar no Postman as APIs de Conta CCME + Internet "
        "Bank a partir da especificação OpenAPI em docs, mapeando os paths "
        "upstream para as rotas bridge de account com bodies alinhados aos "
        "schemas. Validar integração bridge vs spec: conferir routes, "
        "handlers, clients e models; listar gaps se houver; se gap for "
        "bug/falta de rota ou contrato, corrigir com testes; se só docs ou "
        "postman, atualizar a documentação correspondente do repositório."
    )
    # "se gap for bug ... corrigir" é condicional, não o pedido principal.
    assert detect_loop(prompt) is None


def test_prompt_curto_de_bug_continua_ligando_o_loop() -> None:
    assert detect_loop("tem um bug no parser de datas") == "bug"
    assert detect_loop("consertar a falha do cálculo de prazo") == "bug"


def test_regressao_0427_deteccao_original_continua() -> None:
    assert detect_loop("Corrigir o bug do cálculo de prazo") == "bug"
    assert detect_loop("Criar um MVP do zero para agendamento") == "mvp"
    assert detect_loop("Auditar a landing page de vendas") == "landing"
    assert detect_loop("/loop-bug escrever o post sobre o artigo") == "bug"
    assert detect_loop("Renomear a variável x para y") is None


# ------------------------------------------------------------------ bug-046

PROMPT_CRITERIOS_INLINE = (
    "Corrigir o bug do envelope de erro e atualizar exemplos do Postman. "
    "Critérios: testes passam; resposta VALIDATION_FAILED inclui lista de "
    "erros por campo quando upstream envia; Postman PF create body corrigido; "
    "documentação atualizada. Não alterar git config; commit só se pedido."
)


def test_secao_criterios_inline_vira_acs() -> None:
    criteria = parse_criteria_section(PROMPT_CRITERIOS_INLINE)
    descs = [c.description for c in criteria]
    assert len(criteria) == 4
    assert any("VALIDATION_FAILED" in d for d in descs)
    assert any("documentação atualizada" in d for d in descs)
    # "Não alterar git config" está FORA da seção (após o ponto final).
    assert not any("git config" in d for d in descs)


def test_secao_criterios_vence_o_template_do_loop() -> None:
    analysis = TaskAnalyzer().analyze(PROMPT_CRITERIOS_INLINE)
    criteria = CriteriaBuilder().build(PROMPT_CRITERIOS_INLINE, analysis)
    descs = " | ".join(c.description for c in criteria)
    assert "VALIDATION_FAILED" in descs
    # O template do loop de bug ("Defeito reproduzido...") não pode vencer
    # critérios escritos pelo usuário.
    assert "Defeito reproduzido" not in descs


def test_acs_declarados_continuam_vencendo_a_secao() -> None:
    prompt = (
        "Corrigir o bug X.\n"
        "- AC-001: entregar o relatorio da investigacao\n"
        "Critérios: testes passam; docs atualizados.\n"
    )
    analysis = TaskAnalyzer().analyze(prompt)
    criteria = CriteriaBuilder().build(prompt, analysis)
    assert len(criteria) == 1
    assert "relatorio da investigacao" in criteria[0].description


def test_secao_criterios_em_lista_de_bullets() -> None:
    prompt = (
        "Implementar o provider Quod.\n"
        "Critérios de aceitação:\n"
        "- go test nos pacotes novos/alterados passa\n"
        "- go build ./cmd/server\n"
        "- documentação atualizada\n"
        "\n"
        "Workspace: d:/GuardLine.BR/onp-api\n"
    )
    criteria = parse_criteria_section(prompt)
    assert [c.description for c in criteria] == [
        "go test nos pacotes novos/alterados passa",
        "go build ./cmd/server",
        "documentação atualizada",
    ]


def test_sem_secao_nao_muda_nada() -> None:
    assert parse_criteria_section("Renomear a variável x para y") == []
    assert parse_criteria_section("") == []


def test_kinds_da_secao_sao_julgaveis() -> None:
    criteria = parse_criteria_section(PROMPT_CRITERIOS_INLINE)
    # Linguagem natural vira EVIDENCE (julgamento do validador) — nunca um
    # check determinístico que o texto não sustenta.
    assert all(
        c.kind in {CriterionKind.EVIDENCE, CriterionKind.TESTS_PASS}
        for c in criteria
    )


# ------------------------------------------------------------------ bug-047

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@test.local")
    _git(path, "config", "user.name", "test")


@pytest.fixture()
def nested_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Raiz NÃO-git contendo um repo git aninhado (formato GuardLine.BR)."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "workspace"
    root.mkdir()
    child = root / "travelex-api"
    _init_repo(child)
    (child / "main.go").write_text("package main\n", encoding="utf-8")
    _git(child, "add", ".")
    _git(child, "commit", "-q", "-m", "init")
    return root


def test_mudanca_em_repo_aninhado_e_detectada(nested_layout: Path) -> None:
    baseline = capture_baseline(nested_layout)
    (nested_layout / "travelex-api" / "main.go").write_text(
        "package main // changed\n", encoding="utf-8"
    )
    changed = changed_files_since(nested_layout, baseline)
    assert changed == ["travelex-api/main.go"]


def test_arquivo_novo_em_repo_aninhado_e_detectado(nested_layout: Path) -> None:
    baseline = capture_baseline(nested_layout)
    (nested_layout / "travelex-api" / "novo.go").write_text(
        "package main\n", encoding="utf-8"
    )
    changed = changed_files_since(nested_layout, baseline)
    assert changed == ["travelex-api/novo.go"]


def test_sem_mudanca_nao_reporta_nada(nested_layout: Path) -> None:
    baseline = capture_baseline(nested_layout)
    assert changed_files_since(nested_layout, baseline) == []


def test_raiz_git_com_aninhado_reporta_ambos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "mono"
    _init_repo(root)
    (root / "README.md").write_text("root\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")

    child = root / "onp-api"
    _init_repo(child)
    (child / "go.mod").write_text("module onp\n", encoding="utf-8")
    _git(child, "add", ".")
    _git(child, "commit", "-q", "-m", "init")

    baseline = capture_baseline(root)
    (root / "README.md").write_text("root changed\n", encoding="utf-8")
    (child / "go.mod").write_text("module onp // changed\n", encoding="utf-8")

    changed = changed_files_since(root, baseline)
    assert "README.md" in changed
    assert "onp-api/go.mod" in changed


def test_raiz_sem_git_e_sem_aninhados_segue_vazio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "plain"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")
    baseline = capture_baseline(root)
    assert baseline.available is False
    assert changed_files_since(root, baseline) == []


# ------------------------------------------------------------------ bug-048

def test_descoberta_de_testes_desce_em_extra_dirs(tmp_path: Path) -> None:
    from orchestrator_runtime.testing.discovery import TestDiscovery

    root = tmp_path / "mono"
    child = root / "travelex-api"
    child.mkdir(parents=True)
    (child / "go.mod").write_text("module travelex\n", encoding="utf-8")

    # Raiz pasta-mãe: nenhum marcador de stack.
    assert TestDiscovery().discover(root) == []
    # Repo filho tem stack Go.
    found = TestDiscovery().discover(child)
    assert any(t.source == "go.mod" for t in found)


def test_run_all_extra_dirs_roda_no_repo_filho(tmp_path: Path) -> None:
    from orchestrator_runtime.testing.discovery import TestRunner

    root = tmp_path / "mono"
    child = root / "onp-api"
    child.mkdir(parents=True)
    (child / "go.mod").write_text("module onp\n", encoding="utf-8")

    executed: list[tuple[list[str], Path]] = []

    class FakeResult:
        exit_code = 0
        timed_out = False
        stdout = "ok"
        stderr = ""

    class FakeExecutor:
        def run(self, command, cwd=None, timeout_s=None, env=None, allow_nested=False):
            executed.append((list(command), Path(cwd)))
            return FakeResult()

    results = TestRunner(FakeExecutor()).run_all(root, extra_dirs=["onp-api"])
    assert executed, "teste do repo filho precisa rodar"
    assert executed[0][1] == child, "cwd deve ser o repo filho"
    assert any(r["discovery_source"] == "onp-api/go.mod" for r in results)
    assert all(r["status"] == "passed" for r in results)


def test_run_all_sem_nada_segue_reportando_none(tmp_path: Path) -> None:
    from orchestrator_runtime.testing.discovery import TestRunner

    root = tmp_path / "vazio"
    root.mkdir()

    class FakeExecutor:
        def run(self, *a, **k):  # pragma: no cover - não deve ser chamado
            raise AssertionError("nada a executar")

    results = TestRunner(FakeExecutor()).run_all(root, extra_dirs=["nao-existe"])
    assert len(results) == 1
    assert results[0]["command"] == "<none>"
    assert results[0]["status"] == "skipped"


# ------------------------------------------------------------------ bug-049

def test_repara_mojibake_utf8_lido_como_cp1252() -> None:
    from orchestrator_runtime.textutil import repair_mojibake

    original = "REVERTER exigência de X-Idempotency-Key na coleção"
    mojibake = original.encode("utf-8").decode("cp1252")
    assert "Ã" in mojibake  # sanidade: corrompeu mesmo
    assert repair_mojibake(mojibake) == original


def test_texto_legitimo_com_maiusculas_acentuadas_intacto() -> None:
    from orchestrator_runtime.textutil import repair_mojibake

    for text in (
        "NÃO ALTERAR o commit; SÃO PAULO",
        "texto limpo: exigência, coleção, validação",
        "",
    ):
        assert repair_mojibake(text) == text


def test_repara_mojibake_duplo() -> None:
    from orchestrator_runtime.textutil import repair_mojibake

    original = "documentação atualizada"
    double = (
        original.encode("utf-8").decode("cp1252").encode("utf-8").decode("cp1252")
    )
    assert repair_mojibake(double) == original
