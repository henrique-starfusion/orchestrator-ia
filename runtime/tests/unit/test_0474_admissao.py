"""0.4.74 — admissao: quem entra, quem espera, e por que.

A suite toda roda com `max_parallel_tasks: 1`, que e o comportamento da 0.4.73.
Este arquivo e o unico que liga o teto e exercita o caminho concorrente.

Errar aqui tem custo nos DOIS sentidos e os dois sao caros:

- falso "sobrepoe" serializa a frota de volta e nao resolve o problema que
  motivou a feature (a segunda task esperando 25-40 min);
- falso "nao sobrepoe" coloca dois agentes no mesmo arquivo, que e o bug-077
  (seis quase-arrastoes num dia no printbee).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState


def _com_teto(project: Path, teto: int) -> TaskService:
    caminho = project / ".orchestrator" / "config" / "policies.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["max_parallel_tasks"] = teto
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return TaskService(load_config(project, fake_agents=True), verbose=False)


def _ocupa(svc: TaskService, prompt: str, escopo: list[str]) -> str:
    """Cria uma task, declara escopo e a deixa em estado ATIVO."""
    task = svc.create_task(prompt)
    fresh = svc.get(task.id)
    fresh.constraints.scope = escopo
    svc.repo.save(fresh)
    svc.repo.transition(
        svc.get(task.id), TaskState.ANALYZING, reason="ocupando", agent="runtime"
    )
    return task.id


def _candidata(svc: TaskService, prompt: str, escopo: list[str]):
    task = svc.create_task(prompt)
    fresh = svc.get(task.id)
    fresh.constraints.scope = escopo
    svc.repo.save(fresh)
    return svc.get(task.id)


# --------------------------------------------------------------------------
# o teto
# --------------------------------------------------------------------------


def test_teto_1_e_o_comportamento_da_0473(project: Path) -> None:
    svc = _com_teto(project, 1)
    dono = _ocupa(svc, "primeira", ["src/api"])

    bloqueio = svc._blocking_task_id(
        str(project), _candidata(svc, "segunda", ["src/web"])
    )

    assert bloqueio == dono, "com teto 1 nada entra, nem escopo disjunto"


def test_teto_respeitado_mesmo_com_escopo_disjunto(project: Path) -> None:
    """Escopo separa CODIGO; o teto protege a MAQUINA.

    Cada task gasta ~6 invocacoes de CLI, e foi exaustao de recurso que produziu
    o 0xC0000142 do bug-109.
    """
    svc = _com_teto(project, 2)
    _ocupa(svc, "a", ["src/a"])
    _ocupa(svc, "b", ["src/b"])

    bloqueio = svc._blocking_task_id(str(project), _candidata(svc, "c", ["src/c"]))

    assert bloqueio is not None


def test_projeto_livre_admite(project: Path) -> None:
    svc = _com_teto(project, 3)

    assert svc._blocking_task_id(str(project), _candidata(svc, "a", ["src/a"])) is None


# --------------------------------------------------------------------------
# o escopo
# --------------------------------------------------------------------------


def test_escopos_disjuntos_entram_juntos(project: Path) -> None:
    """O ponto da feature."""
    svc = _com_teto(project, 3)
    _ocupa(svc, "api", ["src/api"])

    bloqueio = svc._blocking_task_id(
        str(project), _candidata(svc, "web", ["src/web", "docs"])
    )

    assert bloqueio is None


def test_escopos_sobrepostos_esperam(project: Path) -> None:
    svc = _com_teto(project, 3)
    dono = _ocupa(svc, "api", ["src/api"])

    bloqueio = svc._blocking_task_id(
        str(project), _candidata(svc, "rotas", ["src/api/rotas.py"])
    )

    assert bloqueio == dono


def test_escopo_desconhecido_serializa(project: Path) -> None:
    """Sem declaracao nao ha prova de disjuncao — e sem prova, nao ha vaga."""
    svc = _com_teto(project, 3)
    dono = _ocupa(svc, "api", ["src/api"])

    assert svc._blocking_task_id(str(project), _candidata(svc, "?", [])) == dono


def test_ativa_sem_escopo_bloqueia_todo_mundo(project: Path) -> None:
    """O outro lado da mesma regra: quem ja roda sem escopo pode estar em
    qualquer lugar, entao ninguem pode entrar ao lado dela."""
    svc = _com_teto(project, 3)
    dono = _ocupa(svc, "misteriosa", [])

    assert svc._blocking_task_id(str(project), _candidata(svc, "api", ["src/api"])) == dono


def test_auth_e_authz_nao_colidem(project: Path) -> None:
    """O falso positivo textual, agora ponta a ponta na admissao."""
    svc = _com_teto(project, 3)
    _ocupa(svc, "auth", ["src/auth"])

    bloqueio = svc._blocking_task_id(
        str(project), _candidata(svc, "authz", ["src/authz"])
    )

    assert bloqueio is None


def test_escopo_do_dono_vence_o_do_planner(project: Path) -> None:
    svc = _com_teto(project, 3)
    task = svc.create_task("x")
    fresh = svc.get(task.id)
    fresh.constraints.scope = ["src/dono"]
    fresh.analysis = {"scope": ["src/planner"]}
    svc.repo.save(fresh)

    assert svc.task_scope(svc.get(task.id)) == ("src/dono",)


def test_escopo_do_planner_vale_quando_o_dono_calou(project: Path) -> None:
    svc = _com_teto(project, 3)
    task = svc.create_task("x")
    fresh = svc.get(task.id)
    fresh.analysis = {"scope": ["src/planner"]}
    svc.repo.save(fresh)

    assert svc.task_scope(svc.get(task.id)) == ("src/planner",)


# --------------------------------------------------------------------------
# run_task e a fila
# --------------------------------------------------------------------------


def test_run_task_enfileira_quando_o_escopo_colide(project: Path) -> None:
    svc = _com_teto(project, 3)
    dono = _ocupa(svc, "api", ["src/api"])
    candidata = _candidata(svc, "mesma pasta", ["src/api/rotas.py"])

    asyncio.run(svc.run_task(candidata.id))

    depois = svc.get(candidata.id)
    assert depois.status == TaskState.QUEUED
    assert dono in (depois.error or "")


def test_dequeue_puxa_mais_de_uma_quando_cabe(project: Path) -> None:
    """Antes o dequeue puxava UMA e so com o workspace totalmente livre."""
    svc = _com_teto(project, 3)
    ids = []
    for nome in ("a", "b"):
        t = _candidata(svc, nome, [f"src/{nome}"])
        svc.repo.transition(t, TaskState.QUEUED, reason="fila", agent="runtime")
        ids.append(t.id)
    iniciadas: list[str] = []
    svc._start_background = lambda task_id, *, name: iniciadas.append(task_id)

    svc._maybe_start_next(str(project))

    assert sorted(iniciadas) == sorted(ids)


def test_dequeue_nao_fura_o_teto(project: Path) -> None:
    """`transition` deixa a task em RECEIVED, que NAO e estado ativo, e a thread
    so entra em `_running_tasks` depois. Sem contagem local na propria passada,
    um laco com 3 na fila admitiria as 3 de uma vez."""
    svc = _com_teto(project, 2)
    _ocupa(svc, "ja rodando", ["src/ja"])
    for nome in ("a", "b", "c"):
        t = _candidata(svc, nome, [f"src/{nome}"])
        svc.repo.transition(t, TaskState.QUEUED, reason="fila", agent="runtime")
    iniciadas: list[str] = []
    svc._start_background = lambda task_id, *, name: iniciadas.append(task_id)

    svc._maybe_start_next(str(project))

    assert len(iniciadas) == 1, "teto 2 com 1 rodando: cabe exatamente uma"


def test_dequeue_pula_quem_nao_cabe_e_segue(project: Path) -> None:
    """FIFO estrito deixaria vaga ociosa por causa de uma task que nao pode
    entrar. A varredura ignora quem colide e continua."""
    svc = _com_teto(project, 3)
    _ocupa(svc, "api", ["src/api"])
    colide = _candidata(svc, "colide", ["src/api/x.py"])
    svc.repo.transition(colide, TaskState.QUEUED, reason="fila", agent="runtime")
    cabe = _candidata(svc, "cabe", ["src/web"])
    svc.repo.transition(cabe, TaskState.QUEUED, reason="fila", agent="runtime")
    iniciadas: list[str] = []
    svc._start_background = lambda task_id, *, name: iniciadas.append(task_id)

    svc._maybe_start_next(str(project))

    assert iniciadas == [cabe.id]


# --------------------------------------------------------------------------
# deteccao de desvio — a outra metade da garantia
# --------------------------------------------------------------------------


def test_desvio_de_escopo_vira_degradacao(project: Path) -> None:
    svc = _com_teto(project, 3)
    task = _candidata(svc, "so na api", ["src/api"])
    svc.repo.add_agent_run(
        task_id=task.id,
        role="executor",
        agent="codex",
        status="completed",
        changed_files_json=json.dumps(["src/api/ok.py", "src/web/invadido.py"]),
    )

    assert svc.scope_violations(task.id) == ["src/web/invadido.py"]
    degradacao = [d for d in svc.degradations(task.id) if d["kind"] == "scope_violation"]
    assert degradacao
    assert "src/web/invadido.py" in degradacao[0]["detail"]


def test_sem_escopo_nao_ha_desvio(project: Path) -> None:
    """Acusar desvio de um escopo que ninguem declarou seria ruido."""
    svc = _com_teto(project, 3)
    task = _candidata(svc, "sem escopo", [])
    svc.repo.add_agent_run(
        task_id=task.id,
        role="executor",
        agent="codex",
        status="completed",
        changed_files_json=json.dumps(["qualquer/coisa.py"]),
    )

    assert svc.scope_violations(task.id) == []
    assert not [d for d in svc.degradations(task.id) if d["kind"] == "scope_violation"]


def test_trabalho_dentro_do_escopo_nao_degrada(project: Path) -> None:
    svc = _com_teto(project, 3)
    task = _candidata(svc, "comportada", ["src/api"])
    svc.repo.add_agent_run(
        task_id=task.id,
        role="executor",
        agent="codex",
        status="completed",
        changed_files_json=json.dumps(["src/api/a.py", "src/api/sub/b.py"]),
    )

    assert svc.scope_violations(task.id) == []


# --------------------------------------------------------------------------
# executor por task: so quando ha concorrencia
# --------------------------------------------------------------------------


def test_com_concorrencia_cada_task_tem_seu_executor(project: Path) -> None:
    """`on_heartbeat` e `progress_probe` sao do EXECUTOR. Compartilhado, a
    segunda task a despachar rouba o heartbeat da primeira e substitui a sonda de
    silencio dela — e a sonda decide se um agente calado esta morto (bug-086)."""
    svc = _com_teto(project, 3)
    a = svc.create_task("a")
    b = svc.create_task("b")

    ex_a = svc._task_executor(svc.get(a.id))
    ex_b = svc._task_executor(svc.get(b.id))

    assert ex_a is not ex_b
    assert ex_a is not svc.executor
    assert ex_a._active_pids is not svc.executor._active_pids


def test_sem_concorrencia_o_executor_e_o_compartilhado(project: Path) -> None:
    """Copiar um adapter/executor que guarda estado observavel faz o estado ir
    para a copia. Sem concorrencia nao ha o que isolar, e nao se paga o risco."""
    svc = _com_teto(project, 1)
    task = svc.create_task("a")

    assert svc._task_executor(svc.get(task.id)) is svc.executor


def test_heartbeat_do_agente_registra_no_executor_da_task(project: Path) -> None:
    svc = _com_teto(project, 3)
    a = svc.create_task("a")
    b = svc.create_task("b")

    svc._register_heartbeat(svc.get(a.id), role="executor", agent_id="codex")
    svc._register_heartbeat(svc.get(b.id), role="validator", agent_id="claude")

    ex_a = svc._task_executor(svc.get(a.id))
    ex_b = svc._task_executor(svc.get(b.id))
    assert ex_a.on_heartbeat is not None
    assert ex_b.on_heartbeat is not None
    assert ex_a.on_heartbeat is not ex_b.on_heartbeat
    assert svc.executor.on_heartbeat is None, (
        "com concorrencia o executor compartilhado nao recebe callback de task"
    )
