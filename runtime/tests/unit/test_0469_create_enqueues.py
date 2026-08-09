"""0.4.69 — task nascida com o workspace ocupado entra na FILA (bug-103).

`_enqueue_task` so acontecia dentro do `run_task`. Quem cria por MCP
(`orchestrator_run`, wait=false) ou por `task create` nunca chama `run_task`,
entao a task ficava em RECEIVED — e RECEIVED esta FORA de `list_queued`, ou
seja, a cadeia de dequeue (corrigida no bug-098) nem olhava para ela. Sobrava a
adocao de orfa: uma por vez, so com o workspace livre, e so se alguem fizesse
poll.

Medido no printbee em 09/08:
  edeee9684e66  9899s (2h45min) entre `task_created` e o primeiro estado
  2d933db18554  2h47min com UM unico evento — nunca comecou
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState


def test_workspace_livre_mantem_received(project: Path) -> None:
    """Caminho normal intacto: sem ninguem ocupando, nada de fila."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("primeira, workspace livre")

    assert task.status == TaskState.RECEIVED
    assert not task.error


def test_workspace_ocupado_nasce_em_queued(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    ocupante = svc.create_task("ocupa o workspace")
    svc._running_tasks.add(ocupante.id)

    nova = svc.create_task("nasce com o workspace ocupado")

    assert nova.status == TaskState.QUEUED, (
        "ficou em RECEIVED: fora de list_queued, o dequeue nunca a enxerga"
    )
    assert f"queued_behind:{ocupante.id}" in (nova.error or "")


def test_queued_no_nascimento_entra_na_fila_de_verdade(project: Path) -> None:
    """O ponto todo: tem que aparecer em `list_queued` para o dequeue pegar."""
    svc = build_service(project, fake_agents=True)
    ocupante = svc.create_task("ocupa")
    svc._running_tasks.add(ocupante.id)

    a = svc.create_task("segunda")
    b = svc.create_task("terceira")

    fila = [t.id for t in svc.repo.list_queued(str(project))]
    assert a.id in fila and b.id in fila
    assert fila.index(a.id) < fila.index(b.id), "FIFO: quem chegou antes sai antes"


def test_status_mostra_posicao_na_fila(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    ocupante = svc.create_task("ocupa")
    svc._running_tasks.add(ocupante.id)
    nova = svc.create_task("enfileirada")

    out = svc.status(nova.id)
    assert out["status"] == TaskState.QUEUED.value
    assert out["queue_position"] >= 1
    assert out["blocked_by"] == ocupante.id


async def test_run_task_da_enfileirada_roda_quando_libera(project: Path) -> None:
    """Nascer QUEUED nao pode impedir de rodar: run_task promove e executa."""
    svc = build_service(project, fake_agents=True)
    ocupante = svc.create_task("ocupa")
    svc._running_tasks.add(ocupante.id)
    nova = svc.create_task("enfileirada")
    assert nova.status == TaskState.QUEUED

    svc._running_tasks.discard(ocupante.id)  # workspace liberou
    resultado = await svc.run_task(nova.id)

    assert resultado.status != TaskState.QUEUED, "ficou presa na fila apos liberar"


def test_falha_ao_enfileirar_nao_impede_a_criacao(project: Path, monkeypatch) -> None:
    """Enfileirar e otimizacao; criar a task e o contrato."""
    svc = build_service(project, fake_agents=True)

    def explode(*_a, **_k):
        raise RuntimeError("banco reclamou")

    monkeypatch.setattr(svc, "_busy_task_id", explode)
    task = svc.create_task("criacao tem que sobreviver")

    assert task.id
    assert task.status == TaskState.RECEIVED
