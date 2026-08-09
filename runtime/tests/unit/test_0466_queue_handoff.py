"""0.4.66 — a fila entregava a task e matava quem ia executa-la (bug-098).

`_maybe_start_next` desenfileira e chama `_start_background`, que roda a task
numa thread DAEMON. Quem dispara isso e o `finally` do `run_task` — no CLI, o
processo sai no instante seguinte e leva a thread junto. A task ja tinha sido
transicionada de QUEUED para RECEIVED, entao sai de `list_queued` e ninguem mais
a enxerga pela fila; so a adocao de orfa, que depende de alguem fazer poll.

Medido no printbee: `06d74af53ee0` terminou 17:35:53 e `a0a588e6937b` foi para
RECEIVED no MESMO segundo, ficando 11,5 min parada ate o dono cancelar. Em
07/08 a mesma sequencia durou 47 HORAS, ate o auto-cancel de 6h.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from orchestrator_runtime.tasks.service import build_service


def test_join_background_espera_a_thread_do_dequeue(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    marca: list[str] = []

    def _lento() -> None:
        time.sleep(0.3)
        marca.append("terminou")

    thread = threading.Thread(target=_lento, daemon=True)
    svc._background_threads.append(thread)
    thread.start()

    assert svc.join_background() == 1
    assert marca == ["terminou"], "join_background retornou antes da thread acabar"


def test_join_background_sem_pendencia_e_barato(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    assert svc.join_background() == 0


def test_thread_ja_terminada_nao_conta(project: Path) -> None:
    """So conta o que ainda esta vivo — o relatorio ao dono precisa ser honesto."""
    svc = build_service(project, fake_agents=True)
    thread = threading.Thread(target=lambda: None, daemon=True)
    svc._background_threads.append(thread)
    thread.start()
    thread.join()

    assert svc.join_background() == 0


def test_start_background_registra_para_o_join(project: Path) -> None:
    """O caminho real: quem inicia em background fica rastreado."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task que sera adotada")

    svc._start_background(task.id, name="teste")

    assert len(svc._background_threads) == 1
    svc.join_background(timeout_s=30)


def test_join_background_com_timeout_nao_pendura(project: Path) -> None:
    """Thread que nao termina nao pode prender o CLI para sempre."""
    svc = build_service(project, fake_agents=True)
    parar = threading.Event()
    thread = threading.Thread(target=parar.wait, daemon=True)
    svc._background_threads.append(thread)
    thread.start()
    try:
        inicio = time.monotonic()
        assert svc.join_background(timeout_s=0.2) == 1
        assert time.monotonic() - inicio < 5, "join ignorou o timeout"
    finally:
        parar.set()
