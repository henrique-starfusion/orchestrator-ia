"""0.4.29 (bug-041) — prompt grande nao cabe em argv no Windows.

Medido no printbee em 2026-07-27: `executor-codex.txt` com 30 bytes —
"Linha de comando muito longa." — em DUAS tasks (4d8728e3196a, 715339d2f2e8),
executor E corrector. WinError 206: o CreateProcess do Windows corta a linha de
comando em 32767 chars. Nenhum arquivo foi tocado, e mesmo assim a task seguiu
para validacao e terminou INCOMPLETE com score 0.8 — parecia trabalho ruim, era
processo que nunca nasceu.

Estourou porque desde a 0.4.27 o prompt do executor carrega skills + rules +
loop alem do pedido do usuario. Prompt de usuario de ~6KB ja bastava.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentRequest, AgentSession
from orchestrator_runtime.agents.base_adapters import ARGV_LIMIT, ProfileCliAdapter
from orchestrator_runtime.agents.process import CliExecutor, ProcessResult

CODEX = {
    "id": "codex",
    "kind": "cli",
    "invoke": {"subcommand": ["exec"], "prompt_via": "arg", "prompt_flag": None},
    "exit_codes": {"success": 0},
}
CLAUDE = {
    "id": "claude",
    "kind": "cli",
    "invoke": {"subcommand": [], "prompt_via": "arg", "prompt_flag": "-p"},
    "exit_codes": {"success": 0},
}


class _SpyExecutor(CliExecutor):
    def __init__(self, project: Path) -> None:
        super().__init__(project, echo=False)
        self.calls: list[dict] = []

    def run(self, command, **kwargs):  # type: ignore[override]
        self.calls.append({"command": list(command), "stdin_text": kwargs.get("stdin_text")})
        return ProcessResult(exit_code=0, stdout="ok", stderr="", command=list(command))


def _adapter(profile: dict, project: Path) -> tuple[ProfileCliAdapter, _SpyExecutor]:
    spy = _SpyExecutor(project)
    adapter = ProfileCliAdapter(profile, spy)
    adapter.detect = lambda: type(  # type: ignore[method-assign]
        "S", (), {"available": True, "path": None}
    )()
    return adapter, spy


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [CODEX, CLAUDE], ids=["codex", "claude"])
async def test_prompt_grande_vai_por_stdin(profile: dict, project: Path) -> None:
    adapter, spy = _adapter(profile, project)
    huge = "x" * (ARGV_LIMIT + 5_000)
    request = AgentRequest(role="executor", prompt=huge, cwd=str(project))

    await adapter.continue_session(AgentSession(agent_id=profile["id"], role="executor"), request)

    call = spy.calls[0]
    assert call["stdin_text"] == huge, "prompt grande tem que ir por stdin"
    assert huge not in call["command"], "prompt grande nao pode ir em argv (WinError 206)"
    assert sum(len(a) + 1 for a in call["command"]) <= ARGV_LIMIT


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [CODEX, CLAUDE], ids=["codex", "claude"])
async def test_prompt_pequeno_continua_em_argv(profile: dict, project: Path) -> None:
    """Caminho normal intacto: sem stdin, sem mudanca de comportamento."""
    adapter, spy = _adapter(profile, project)
    request = AgentRequest(role="executor", prompt="corrigir bug X", cwd=str(project))

    await adapter.continue_session(AgentSession(agent_id=profile["id"], role="executor"), request)

    call = spy.calls[0]
    assert call["stdin_text"] is None
    assert "corrigir bug X" in call["command"]


@pytest.mark.asyncio
async def test_prompt_via_stdin_no_profile_e_respeitado(project: Path) -> None:
    """Profile pode forcar stdin mesmo com prompt curto."""
    profile = {**CODEX, "invoke": {**CODEX["invoke"], "prompt_via": "stdin"}}
    adapter, spy = _adapter(profile, project)
    request = AgentRequest(role="executor", prompt="curto", cwd=str(project))

    await adapter.continue_session(AgentSession(agent_id="codex", role="executor"), request)

    assert spy.calls[0]["stdin_text"] == "curto"
    assert "curto" not in spy.calls[0]["command"]


@pytest.mark.asyncio
async def test_cli_sem_stdin_nao_perde_o_texto(project: Path) -> None:
    """`kimi -p <prompt>` exige o valor: `-p` vazio seria comando invalido.

    Melhor estourar no argv com WinError 206 — que desde a 0.4.30 se explica —
    do que montar um comando que o CLI recusa.
    """
    kimi = {
        "id": "kimi",
        "kind": "cli",
        "invoke": {"subcommand": [], "prompt_flag": "-p", "prompt_stdin": False},
        "exit_codes": {"success": 0},
    }
    adapter, spy = _adapter(kimi, project)
    huge = "x" * (ARGV_LIMIT + 5_000)
    request = AgentRequest(role="executor", prompt=huge, cwd=str(project))

    await adapter.continue_session(AgentSession(agent_id="kimi", role="executor"), request)

    call = spy.calls[0]
    assert call["stdin_text"] is None
    assert huge in call["command"], "prompt nao pode sumir do argv quando stdin nao serve"


def test_flag_de_prompt_sobrevive_sem_o_texto(project: Path) -> None:
    """`claude -p` sem valor le stdin; a flag nao pode sumir junto com o texto."""
    adapter, _ = _adapter(CLAUDE, project)
    request = AgentRequest(role="executor", prompt="qualquer", cwd=str(project))

    argv = adapter.build_command(request, prompt_in_argv=False)

    assert "-p" in argv
    assert "qualquer" not in argv
