"""0.4.28 — plano incompleto manda CONTINUAR em vez de validar pela metade.

Comportamento padrao de Claude/Codex/qualquer CLI: em plano longo o agente para
no meio e pergunta se deve seguir. O runtime tratava isso como execucao
terminada e ia validar trabalho parcial. Agora ele verifica se o plano fechou;
se nao, reenvia mandando continuar de onde parou (sem queimar iteracao de
validacao) ate o orcamento de continuacoes.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState

S = TaskService


# ------------------------------------------------------- deteccao

def test_plan_status_completo_nao_continua() -> None:
    out = 'fiz tudo\nPLAN_STATUS: {"complete": true}'
    assert S._parse_plan_status(out) == {"complete": True}
    assert S._is_plan_incomplete(S._parse_plan_status(out), out) is False


def test_plan_status_incompleto_continua() -> None:
    out = 'parei\nPLAN_STATUS: {"complete": false, "remaining": ["etapa 4", "testes"]}'
    status = S._parse_plan_status(out)
    assert status["remaining"] == ["etapa 4", "testes"]
    assert S._is_plan_incomplete(status, out) is True


def test_frases_de_parada_sem_plan_status() -> None:
    for out in (
        "Implementei as etapas 1 a 3. Quer que eu continue?",
        "Concluí a parte 1 de 3.",
        "Shall I continue with the remaining files?",
        "Let me know if you'd like me to implement the rest.",
        "Próximos passos: aplicar no handler",
        "Ainda falta implementar o cache",
    ):
        assert S._is_plan_incomplete(None, out) is True, out


def test_saida_normal_nao_e_falso_positivo() -> None:
    for out in (
        "Implementei o handler, adicionei o teste e a suite passou.",
        "Corrigido em 3 arquivos; npm test verde.",
        "",
    ):
        assert S._is_plan_incomplete(None, out) is False, out


def test_plan_status_malformado_cai_no_fallback() -> None:
    out = "PLAN_STATUS: {isso nao e json}\nQuer que eu continue?"
    assert S._parse_plan_status(out) is None
    assert S._is_plan_incomplete(None, out) is True


def test_nota_de_continuacao_diz_o_que_falta() -> None:
    nota = S._continuation_note(["etapa 4", "testes"], ["a.py", "b.py"], 2)
    assert "CONTINUACAO 2" in nota
    assert "NAO recomece" in nota
    assert "etapa 4" in nota and "a.py" in nota
    assert "continue" in nota.lower()


# ------------------------------------------------------- e2e

class StopsHalfwayExecutor(FakeAgentAdapter):
    """Para no meio nas 2 primeiras vezes; conclui na terceira."""

    def __init__(self, agent_id: str, project_path: Path) -> None:
        super().__init__(agent_id, project_path)
        self.executor_calls = 0

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role not in {"executor", "corrector"}:
            return await super().continue_session(session, request)
        self.executor_calls += 1
        (self.project_path / f"parte{self.executor_calls}.py").write_text(
            f"# parte {self.executor_calls}\n", encoding="utf-8"
        )
        if self.executor_calls < 3:
            body = (
                f"Implementei a parte {self.executor_calls} de 3.\n"
                'PLAN_STATUS: {"complete": false, "remaining": ["resto do plano"]}'
            )
        else:
            body = 'Tudo pronto.\nPLAN_STATUS: {"complete": true}'
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="completed",
            exit_code=0,
            stdout=body,
            stderr="",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def test_runtime_manda_continuar_ate_o_plano_fechar(project: Path) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    ex = StopsHalfwayExecutor("claude", project)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = ex

    task = service.create_task("Implementar o plano completo", max_iterations=1)
    asyncio.run(service.run_task(task.id))

    # 3 chamadas ao executor com UMA unica iteracao de validacao permitida:
    # as 2 continuacoes nao podem ter queimado iteracao.
    assert ex.executor_calls == 3, f"executor chamado {ex.executor_calls}x"
    final = service.get(task.id)
    assert final.iteration <= 1, f"continuacao queimou iteracao (iter={final.iteration})"
    assert final.status != TaskState.EXECUTING


def test_orcamento_de_continuacoes_e_respeitado(project: Path) -> None:
    """Executor que NUNCA fecha o plano nao pode rodar para sempre."""
    config = load_config(project, fake_agents=True)
    config.limits.max_plan_continuations = 2
    service = TaskService(config, verbose=False)

    class NeverFinishes(StopsHalfwayExecutor):
        async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
            if request.role not in {"executor", "corrector"}:
                return await super(StopsHalfwayExecutor, self).continue_session(
                    session, request
                )
            self.executor_calls += 1
            (self.project_path / f"x{self.executor_calls}.py").write_text("x\n", encoding="utf-8")
            return AgentResult(
                session_id=session.id,
                agent_id=self.id,
                role=request.role,
                status="completed",
                exit_code=0,
                stdout='PLAN_STATUS: {"complete": false, "remaining": ["sempre falta"]}',
                stderr="",
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )

    ex = NeverFinishes("claude", project)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = ex

    task = service.create_task("Plano que nunca fecha", max_iterations=1)
    asyncio.run(service.run_task(task.id))

    # 1 execucao + 2 continuacoes = 3; depois segue para validacao.
    assert ex.executor_calls == 3, f"executor chamado {ex.executor_calls}x"
    assert service.get(task.id).status in {
        TaskState.COMPLETED, TaskState.INCOMPLETE, TaskState.FAILED
    }
