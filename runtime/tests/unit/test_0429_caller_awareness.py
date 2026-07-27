"""0.4.29 — o orquestrador sabe quem o chamou e ajusta o tratamento.

Superficies tem contratos diferentes: Claude Code bloqueia e precisa de saida ao
vivo; Cursor e MCP fazem polling e dependem dos EVENTOS. E o CLI que ja esta
atendendo o usuario nao deve virar executor sem necessidade — disputa cota do
mesmo provedor.
"""

from __future__ import annotations

from orchestrator_runtime.callers import (
    MCP_ENV,
    OVERRIDE_ENV,
    caller_profile,
    detect_caller,
)


def test_detecta_claude_code() -> None:
    assert detect_caller({"CLAUDECODE": "1"}) == "claude-code"
    assert detect_caller({"CLAUDE_PROJECT_DIR": "D:/x"}) == "claude-code"


def test_detecta_cursor() -> None:
    assert detect_caller({"CURSOR_TRACE_ID": "abc"}) == "cursor"
    assert detect_caller({"TERM_PROGRAM": "cursor"}) == "cursor"


def test_detecta_mcp_e_codex() -> None:
    assert detect_caller({MCP_ENV: "1"}) == "mcp"
    assert detect_caller({"CODEX_HOME": "C:/x"}) == "codex"


def test_cli_e_o_default() -> None:
    assert detect_caller({}) == "cli"


def test_override_explicito_vence() -> None:
    env = {OVERRIDE_ENV: "cursor", "CLAUDECODE": "1", MCP_ENV: "1"}
    assert detect_caller(env) == "cursor"


def test_override_invalido_e_ignorado() -> None:
    assert detect_caller({OVERRIDE_ENV: "inexistente", "CLAUDECODE": "1"}) == "claude-code"


def test_mcp_vence_marcador_de_cliente() -> None:
    """O servidor MCP marca a origem; o env do cliente pode estar herdado."""
    assert detect_caller({MCP_ENV: "1", "CLAUDECODE": "1"}) == "mcp"


def test_perfil_sem_console_nao_ecoa() -> None:
    for cid in ("mcp", "cursor"):
        p = caller_profile(cid)
        assert p.echo is False, cid
        assert p.polls is True, cid


def test_perfil_bloqueante_ecoa_e_bate_mais_rapido() -> None:
    p = caller_profile("claude-code")
    assert p.echo is True
    assert p.polls is False
    assert p.heartbeat_s < caller_profile("mcp").heartbeat_s


def test_agente_ocupado_por_superficie() -> None:
    assert caller_profile("claude-code").busy_agent == "claude"
    assert caller_profile("codex").busy_agent == "codex"
    assert caller_profile("cli").busy_agent is None


def test_perfil_desconhecido_cai_em_cli() -> None:
    p = caller_profile("superficie-que-nao-existe")
    assert p.id == "cli"
    assert p.echo is True
