"""0.4.27 — classificacao por INTENCAO, nao por mencao solta.

Caso real (printbee, task 715339d2f2e8): prompt de 10.523 chars de implementacao
backend foi classificado como security_review porque a palavra "seguranca"
aparecia duas vezes descrevendo a CONSEQUENCIA do bug ("o cliente forja 'admin'
-> falha de seguranca"). O match era substring sobre o prompt inteiro, era o
primeiro ramo do if, e security_review/architecture eram imunes ao override de
intencao de implementacao.
"""

from __future__ import annotations

from orchestrator_runtime.planning.analyzer import TaskAnalyzer

A = TaskAnalyzer()

PRINTBEE_TRECHO = (
    "IMPLEMENTACAO DE CODIGO (nao e analise). Backend WP-2: o handler chamador "
    "passa o storeId. Se vier do body, o cliente forja 'admin' -> falha de "
    "seguranca. Default = Store. WP-2 tambem corrige VAZAMENTO DE SEGURANCA "
    "REAL: hoje o SuperFrete cai em config global. Implementar e testar."
)


def test_mencao_incidental_a_seguranca_nao_vira_security_review() -> None:
    analysis = A.analyze(PRINTBEE_TRECHO)
    assert analysis.task_type == "implementation"


def test_mencao_a_seguranca_ainda_eleva_o_risco() -> None:
    """Perder o sinal de risco seria trocar um erro por outro."""
    assert A.analyze(PRINTBEE_TRECHO).risk == "high"


def test_pedido_real_de_revisao_de_seguranca_continua_classificando() -> None:
    for prompt in (
        "Revisar a seguranca do modulo de autenticacao",
        "Fazer uma auditoria de seguranca no endpoint de pagamento",
        "Security review of the checkout flow",
        "Rodar um pentest na API publica",
        "Avaliar vulnerabilidades do upload de arquivos",
    ):
        assert A.analyze(prompt).task_type == "security_review", prompt


def test_verbo_de_implementacao_vence_security_review() -> None:
    a = A.analyze("Implementar validacao de seguranca no endpoint de login")
    assert a.task_type == "implementation"
    assert a.risk == "high", "continua sendo trabalho sensivel"


def test_design_cru_nao_vira_architecture() -> None:
    for prompt in (
        "Ajustar o design system dos botoes do backoffice",
        "Falar com o designer sobre o espacamento",
        "Redesign da tela de login em Angular",
    ):
        assert A.analyze(prompt).task_type != "architecture", prompt


def test_pedido_real_de_arquitetura_continua_classificando() -> None:
    for prompt in (
        "Definir a arquitetura de mensageria do servico",
        "Propor o desenho da solucao de multi-tenant",
        "Architecture review of the ingestion pipeline",
    ):
        assert A.analyze(prompt).task_type == "architecture", prompt


def test_bug_fix_que_cita_vulnerabilidade_e_implementacao() -> None:
    a = A.analyze("Corrigir a vulnerabilidade de XSS no campo de comentario")
    assert a.task_type == "implementation"
    assert a.risk == "high"
    assert a.loop == "bug"
