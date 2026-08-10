"""0.4.76 — dois defeitos de runtime medidos em producao na 0.4.75.

BUG A (printbee, task e9803cf77a43, 10/08 19:50)
------------------------------------------------
Task orfanada em VALIDATING (o processo dono morreu) foi retomada e terminou::

    status=FAILED  error='Transicao invalida: VALIDATING -> RETRIEVING_MEMORY'

`can_resume` aceita QUALQUER estado nao-terminal, mas `_execute_loop` so
transicionava para ANALYZING vindo de RECEIVED ou WAITING_FOR_USER. Retomando de
VALIDATING o loop pulava a re-entrada, seguia o fluxo e batia no
`transition(RETRIEVING_MEMORY)` partindo de VALIDATING — aresta que nao existe.
O dono recebia um texto que parece merito e era infra.

BUG B (trustsafe, 5 tasks INCOMPLETE em 10/08)
----------------------------------------------
    error='AGENT-FAILED-NO-OUTPUT: corrector/codex exit=3221225794 sem mudancas'

3221225794 = 0xC0000142 STATUS_DLL_INIT_FAILED: o processo NAO NASCEU (a maquina
estava com ~132 processos node vivos). `classify_agent_failure` ja devolvia
`launch`, mas o ramo do servico so emitia evento e devolvia a mesma falha: ela
descia para o guard `failed_no_output`, QUEIMAVA uma iteracao e disparava
fallback para outro agente — que tambem nao nascia, porque a falta de recurso e
da MAQUINA. Falha de lancamento e transiente: o remedio e esperar e tentar de
novo o MESMO agente.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService, build_service
from orchestrator_runtime.tasks.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    TaskState,
)

DLL_INIT_FAILED = 0xC0000142  # 3221225794

PROMPT = "Crie um modulo Python com funcao soma, testes e documentacao"

# Caminho real ate VALIDATING, aresta por aresta (nenhum atalho no DB).
CAMINHO_ATE_VALIDATING = (
    TaskState.ANALYZING,
    TaskState.RETRIEVING_MEMORY,
    TaskState.PLANNING,
    TaskState.SELECTING_AGENTS,
    TaskState.EXECUTING,
    TaskState.TESTING,
    TaskState.VALIDATING,
)

# Estados de meio de pipeline: todo nao-terminal que nao e ponto de entrada.
MEIO_DE_PIPELINE = tuple(
    s
    for s in TaskState
    if s not in TERMINAL_STATES
    and s
    not in {
        TaskState.RECEIVED,
        TaskState.QUEUED,
        TaskState.WAITING_FOR_USER,
        TaskState.ANALYZING,
    }
)


# ---------------------------------------------------------------------------
# BUG A — resume de estado de meio de pipeline
# ---------------------------------------------------------------------------


def test_a_reentrada_para_analyzing_existe_em_todo_estado_de_meio(
    project: Path,
) -> None:
    """A aresta que faltava. VALIDATING -> ANALYZING era a do printbee."""
    for estado in MEIO_DE_PIPELINE:
        assert TaskState.ANALYZING in ALLOWED_TRANSITIONS[estado], estado.value


def test_a_resume_de_validating_nao_mata_a_task(project: Path) -> None:
    """Reproducao do e9803cf77a43: retomar de VALIDATING nao pode virar FAILED."""
    service = build_service(project, fake_agents=True, verbose=False)
    task = service.create_task(PROMPT, max_iterations=2)
    for estado in CAMINHO_ATE_VALIDATING:
        service.repo.transition(task, estado, reason="simula pipeline")
        task = service.get(task.id)
    assert task.status == TaskState.VALIDATING

    done = asyncio.run(service.resume(task.id))

    assert done.status != TaskState.FAILED, done.error
    assert "Transi" not in (done.error or ""), done.error
    assert done.status == TaskState.COMPLETED


def test_a_reentrada_aparece_no_historico_com_motivo_proprio(project: Path) -> None:
    """`task logs` tem que dizer que foi orfa retomada, nao 'start analysis'."""
    service = build_service(project, fake_agents=True, verbose=False)
    task = service.create_task(PROMPT, max_iterations=2)
    for estado in CAMINHO_ATE_VALIDATING:
        service.repo.transition(task, estado, reason="simula pipeline")
        task = service.get(task.id)

    asyncio.run(service.resume(task.id))

    motivos = [
        (e["data"] or {}).get("reason") or ""
        for e in service.repo.list_events(task.id)
        if e.get("type") == "state_changed"
        and (e["data"] or {}).get("to") == TaskState.ANALYZING.value
    ]
    assert any("orphan" in m for m in motivos), motivos


def test_a_estado_terminal_continua_imutavel() -> None:
    """Afrouxar a re-entrada nao pode abrir saida de estado terminal."""
    for estado in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[estado] == set(), estado.value


# ---------------------------------------------------------------------------
# BUG B — falha de lancamento reexecuta o MESMO agente
# ---------------------------------------------------------------------------


class LaunchFailsThenWorks(FakeAgentAdapter):
    """Primeiras N chamadas de escrita nao nascem (0xC0000142); depois roda."""

    def __init__(
        self,
        agent_id: str,
        project_path: Path,
        falhas: int = 1,
        chamadas: list[str] | None = None,
    ) -> None:
        super().__init__(agent_id, project_path)
        self._restantes = falhas
        # Lista COMPARTILHADA entre os adapters: a ordem global é a prova de
        # que o retry veio antes do fallback.
        self.chamadas: list[str] = [] if chamadas is None else chamadas

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role not in {"executor", "corrector"}:
            return await super().continue_session(session, request)
        self.chamadas.append(f"{self.id}/{request.role}")
        if self._restantes > 0:
            self._restantes -= 1
            agora = datetime.now(timezone.utc).isoformat()
            return AgentResult(
                session_id=session.id,
                agent_id=self.id,
                role=request.role,
                status="failed",
                exit_code=DLL_INIT_FAILED,
                stdout="",
                stderr="",
                changed_files=[],
                duration_s=0.0,
                started_at=agora,
                finished_at=agora,
            )
        return await super().continue_session(session, request)


def _servico_sem_espera(
    project: Path, falhas: int
) -> tuple[TaskService, list[str]]:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    chamadas: list[str] = []
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = LaunchFailsThenWorks(
            name, project, falhas=falhas, chamadas=chamadas
        )
    # Backoff real e de segundos; aqui so importa QUE ele tentou de novo.
    service._LAUNCH_RETRY_BACKOFF_S = (0.0, 0.0, 0.0)
    return service, chamadas


def test_b_falha_de_lancamento_isolada_nao_queima_iteracao(project: Path) -> None:
    """Reproducao do trustsafe: 1 lancamento falho seguido de sucesso."""
    service, chamadas = _servico_sem_espera(project, falhas=1)
    task = service.create_task(PROMPT, max_iterations=3)

    done = asyncio.run(service.run_task(task.id))

    assert "AGENT-FAILED-NO-OUTPUT" not in (done.error or "")
    assert done.status == TaskState.COMPLETED, done.error
    assert done.iteration == 1, "falha de lancamento nao pode queimar iteracao"


def test_b_reexecuta_o_mesmo_agente_antes_de_qualquer_fallback(
    project: Path,
) -> None:
    service, chamadas = _servico_sem_espera(project, falhas=1)
    task = service.create_task(PROMPT, max_iterations=3)

    asyncio.run(service.run_task(task.id))

    assert len(chamadas) >= 2, chamadas
    # As duas primeiras sao o MESMO agente: o retry vem antes do fallback.
    assert chamadas[0].split("/")[0] == chamadas[1].split("/")[0], chamadas


def test_b_cada_tentativa_aparece_em_task_logs(project: Path) -> None:
    service, chamadas = _servico_sem_espera(project, falhas=1)
    task = service.create_task(PROMPT, max_iterations=3)

    asyncio.run(service.run_task(task.id))

    dados = [
        e["data"] or {}
        for e in service.repo.list_events(task.id)
        if e.get("type") == "agent_repair"
        and (e["data"] or {}).get("failure_kind") == "launch"
    ]
    assert dados, "falha de lancamento tem que aparecer em `task logs`"
    assert any(d.get("retry_attempt") for d in dados), dados


def test_b_lancamento_que_nunca_nasce_continua_infra_e_nunca_merito(
    project: Path,
) -> None:
    """Esgotar as tentativas nao pode virar julgamento de merito."""
    service, _ = _servico_sem_espera(project, falhas=99)
    task = service.create_task(PROMPT, max_iterations=2)

    done = asyncio.run(service.run_task(task.id))

    assert done.status == TaskState.INCOMPLETE
    assert "AGENT-FAILED-NO-OUTPUT" in (done.error or ""), done.error
    assert str(DLL_INIT_FAILED) in (done.error or ""), done.error
