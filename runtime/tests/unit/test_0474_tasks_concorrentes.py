"""0.4.74 — mais de uma task por projeto, sem dois agentes na mesma arvore.

Ate a 0.4.73 o projeto era serializado por tres camadas: o `WriteLock` segurado
durante TODO o `_execute_loop`, o `find_active_execution` (uma task ativa por
projeto) e a fila FIFO. Isso tornava impossivel dois agentes se atrapalharem —
e tornava o desenvolvimento lento, porque a segunda task esperava a primeira
terminar inteira (25-40 min).

Duas coisas estavam escondidas atras dessa serializacao, e as duas corromperiam
dado em silencio no primeiro instante de concorrencia:

1. Estado do run vivia no SERVICO (`_run_ctx`, `_git_baseline`,
   `_loop_started_monotonic`, `_exhausted_models`, `_current_agent`). O servidor
   MCP roda todas as tasks no mesmo processo, e `_execute_loop` reatribuia os
   quatro primeiros no topo: a task B zerava o relogio, o baseline git e o
   contexto da task A. Nao da erro — atribui arquivo mudado a task errada e
   grava learning com contexto de outra.
2. SQLite sem WAL. O default (`journal_mode=delete`) trava o arquivo inteiro por
   escrita: o segundo escritor leva `database is locked` na hora.
"""

from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import text

from orchestrator_runtime.events import EventType, RuntimeEvent
from orchestrator_runtime.memory.database import SQLITE_BUSY_TIMEOUT_MS
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.service import build_service


# --------------------------------------------------------------------------
# SQLite preparado para varios escritores
# --------------------------------------------------------------------------


def test_banco_em_wal(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    svc.create_task("x")

    with svc.repo.session() as s:
        modo = s.execute(text("PRAGMA journal_mode")).scalar()

    assert str(modo).lower() == "wal", (
        "sem WAL o segundo escritor leva 'database is locked' na hora"
    )


def test_busy_timeout_configurado(project: Path) -> None:
    """Escritor tem que ESPERAR sua vez, nao estourar."""
    svc = build_service(project, fake_agents=True)
    svc.create_task("x")

    with svc.repo.session() as s:
        timeout = int(s.execute(text("PRAGMA busy_timeout")).scalar() or 0)

    assert timeout == SQLITE_BUSY_TIMEOUT_MS


def test_escritores_concorrentes_no_mesmo_banco(project: Path) -> None:
    """O caso real: N tasks gravando evento ao mesmo tempo no mesmo arquivo."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    caminho = str(svc.config.db_path)
    erros: list[BaseException] = []

    def _gravar(indice: int) -> None:
        try:
            repo = TaskRepository(caminho)
            for i in range(20):
                repo.add_event(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.LOOP_PROGRESS,
                        data={"escritor": indice, "n": i},
                    )
                )
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [threading.Thread(target=_gravar, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not erros, f"escrita concorrente falhou: {erros[:2]}"
    gravados = [
        e
        for e in svc.repo.list_events(task.id)
        if e["type"] == EventType.LOOP_PROGRESS.value
    ]
    assert len(gravados) == 80


# --------------------------------------------------------------------------
# contexto por task: nada vaza de um run para o outro
# --------------------------------------------------------------------------


def test_contexto_e_por_task(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    a = svc.create_task("a")
    b = svc.create_task("b")

    svc._ctx(a).run_ctx["changed_files"] = ["a.py"]
    svc._ctx(b).run_ctx["changed_files"] = ["b.py"]

    assert svc._ctx(a).run_ctx["changed_files"] == ["a.py"]
    assert svc._ctx(b).run_ctx["changed_files"] == ["b.py"]


def test_relogio_de_uma_task_nao_reinicia_o_da_outra(project: Path) -> None:
    """`_remaining_duration_s` lia um relogio do servico: a task que comecasse
    depois devolvia orcamento cheio para a que ja estava rodando ha 40 min."""
    svc = build_service(project, fake_agents=True)
    a = svc.create_task("a")
    b = svc.create_task("b")
    svc._ctx(a).started_monotonic -= 3600  # A rodando ha uma hora

    restante_a = svc._remaining_duration_s(svc.get(a.id))
    restante_b = svc._remaining_duration_s(svc.get(b.id))

    assert restante_a < restante_b


def test_modelo_esgotado_nao_vaza_entre_tasks(project: Path) -> None:
    """0.4.25 marca (agent, model) sem cota. Compartilhar isso entre tasks fazia
    uma task herdar a restricao da outra sem nunca ter batido na cota."""
    svc = build_service(project, fake_agents=True)
    a = svc.create_task("a")
    b = svc.create_task("b")

    svc._ctx(a).exhausted_models.add(("claude", "opus"))

    assert ("claude", "opus") in svc._ctx(a).exhausted_models
    assert ("claude", "opus") not in svc._ctx(b).exhausted_models


def test_baseline_git_e_por_task(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    a = svc.create_task("a")
    b = svc.create_task("b")

    svc._ctx(a).git_baseline.available = True
    svc._ctx(b).git_baseline.available = False

    assert svc._ctx(a).git_baseline.available is True
    assert svc._ctx(b).git_baseline.available is False


def test_contexto_novo_a_cada_pedido_nao_apaga_o_existente(project: Path) -> None:
    """`_ctx` cria sob demanda (thread do heartbeat, poll de outro processo) —
    mas nao pode zerar o que ja existe."""
    svc = build_service(project, fake_agents=True)
    a = svc.create_task("a")
    svc._ctx(a).run_ctx["marca"] = 1

    assert svc._ctx(a).run_ctx.get("marca") == 1
