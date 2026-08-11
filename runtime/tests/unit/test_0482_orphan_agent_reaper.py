"""0.4.82 - ceifa automatica de CLI de agente orfao (bug-119).

O executor registrava os PIDs dos CLIs que lancava num set EM MEMORIA
(`CliExecutor._active_pids`), consumido so por `kill_active()` no cancelamento
ordenado. Orfao e, por definicao, o caso em que o rastreador ja se foi: runtime
morto por crash, `taskkill`, restart do editor ou fim abrupto do terminal deixa
os CLIs vivos e NENHUM codigo do orquestrador sabe que eles existem.

Os testes deste arquivo usam PROCESSOS DE VERDADE. O mais importante e o de
reuso de PID: o Windows recicla numero de processo, entao matar por numero e
destrutivo — a identidade registrada (nome da imagem + instante de criacao)
tem que conferir antes de qualquer kill.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.agents.process import CliExecutor
from orchestrator_runtime.agents.reaper import (
    ProcessIdentity,
    identity_matches,
    process_identity,
)
from orchestrator_runtime.tasks.service import TaskService, build_service
from orchestrator_runtime.tasks.state_machine import TaskState
from orchestrator_runtime.memory.database import TaskRow


PROMPT = "Crie um modulo Python com funcao soma, testes e documentacao"


# ---------------------------------------------------------------- utilidades


@pytest.fixture
def sleeper():
    """Processos reais de longa duracao, mortos no teardown do teste."""
    criados: list[subprocess.Popen] = []

    def _spawn() -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(600)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        criados.append(proc)
        return proc

    yield _spawn

    for proc in criados:
        if proc.poll() is None:
            try:
                CliExecutor._kill_tree(proc.pid)
            except Exception:  # noqa: BLE001
                pass
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass


def _dead_pid() -> int:
    """PID de um processo que ja terminou (o dono morto dos cenarios)."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.wait(timeout=30)
    return proc.pid


def _service(project: Path, *, reap_after_s: int = 0) -> TaskService:
    policies_path = project / ".orchestrator" / "config" / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["orphan_agent_reap_after_s"] = reap_after_s
    policies_path.write_text(json.dumps(policies), encoding="utf-8")
    return build_service(project, fake_agents=True, verbose=False)


def _task(service: TaskService, status: TaskState) -> str:
    task = service.create_task(PROMPT, dry_run=True)
    with service.repo.session() as session:
        row = session.get(TaskRow, task.id)
        assert row is not None
        row.status = status.value
        session.commit()
    return task.id


def _register(
    service: TaskService,
    *,
    task_id: str,
    pid: int,
    image: str,
    create_time: float,
    owner_pid: int,
    age_s: int = 600,
) -> None:
    started = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    service.repo.add_agent_process(
        task_id=task_id,
        project_path=str(service.config.project_path),
        role="executor",
        agent="codex",
        pid=pid,
        image=image,
        create_time=create_time,
        owner_pid=owner_pid,
        started_at=started.isoformat(),
    )


def _morreu(proc: subprocess.Popen, timeout: float = 20.0) -> bool:
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


# ------------------------------------------------------- identidade do S.O.


def test_process_identity_le_imagem_e_instante_de_criacao(sleeper) -> None:
    proc = sleeper()
    ident = process_identity(proc.pid)
    assert ident is not None, "identidade do proprio S.O. tem que estar disponivel"
    assert ident.image, "nome da imagem vazio"
    assert ident.create_time > 0
    # Leitura estavel: duas leituras do mesmo processo batem.
    again = process_identity(proc.pid)
    assert again is not None
    assert identity_matches(ident.image, ident.create_time, again)


def test_identity_matches_exige_os_dois_campos() -> None:
    atual = ProcessIdentity(image="codex.exe", create_time=1000.0)
    assert identity_matches("codex.exe", 1000.0, atual)
    assert identity_matches("CODEX.EXE", 1000.0, atual)  # imagem e case-insensitive
    assert not identity_matches("codex.exe", 1600.0, atual)  # instante diferente
    assert not identity_matches("notepad.exe", 1000.0, atual)  # imagem diferente
    assert not identity_matches("codex.exe", 1000.0, None)  # pid sem identidade


def test_process_identity_de_pid_morto_e_none() -> None:
    assert process_identity(_dead_pid()) is None


# ------------------------------------------------------------------- ceifa


def test_ceifa_cli_de_agente_com_runtime_dono_morto_e_task_terminal(
    project: Path, sleeper
) -> None:
    """AC-1 — o caso do bug: ninguem em memoria sabe que este processo existe."""
    service = _service(project)
    proc = sleeper()
    ident = process_identity(proc.pid)
    assert ident is not None
    task_id = _task(service, TaskState.COMPLETED)
    _register(
        service,
        task_id=task_id,
        pid=proc.pid,
        image=ident.image,
        create_time=ident.create_time,
        owner_pid=_dead_pid(),
    )

    ceifados = service._reap_orphan_agents(str(service.config.project_path))

    assert proc.pid in ceifados
    assert _morreu(proc), "CLI orfao continuou vivo"


def test_pid_reciclado_por_outro_programa_nao_e_morto(
    project: Path, sleeper
) -> None:
    """AC-2 — o teste mais importante: numero de PID nao autoriza kill.

    Windows recicla PID. Aqui o registro tem o numero certo e a identidade
    errada (instante de criacao de outro processo, que e o que acontece quando
    o numero foi reaproveitado). Divergencia de identidade impede o kill.
    """
    service = _service(project)
    alheio = sleeper()
    ident = process_identity(alheio.pid)
    assert ident is not None
    task_id = _task(service, TaskState.COMPLETED)
    _register(
        service,
        task_id=task_id,
        pid=alheio.pid,
        image=ident.image,
        create_time=ident.create_time - 3600.0,  # nasceu 1h antes: nao e o nosso
        owner_pid=_dead_pid(),
    )

    ceifados = service._reap_orphan_agents(str(service.config.project_path))

    assert ceifados == []
    assert alheio.poll() is None, "processo alheio foi morto por reuso de PID"


def test_imagem_divergente_nao_e_morta(project: Path, sleeper) -> None:
    """AC-2 (segundo eixo) — instante bate, nome da imagem nao."""
    service = _service(project)
    alheio = sleeper()
    ident = process_identity(alheio.pid)
    assert ident is not None
    task_id = _task(service, TaskState.COMPLETED)
    _register(
        service,
        task_id=task_id,
        pid=alheio.pid,
        image="programa-de-outra-pessoa.exe",
        create_time=ident.create_time,
        owner_pid=_dead_pid(),
    )

    assert service._reap_orphan_agents(str(service.config.project_path)) == []
    assert alheio.poll() is None


def test_task_em_execucao_com_runtime_vivo_nao_e_tocada(
    project: Path, sleeper
) -> None:
    """AC-3 — trabalho em andamento e intocavel."""
    service = _service(project)
    proc = sleeper()
    ident = process_identity(proc.pid)
    assert ident is not None
    task_id = _task(service, TaskState.EXECUTING)
    _register(
        service,
        task_id=task_id,
        pid=proc.pid,
        image=ident.image,
        create_time=ident.create_time,
        owner_pid=os.getpid(),  # o dono e este processo, que esta vivo
    )

    assert service._reap_orphan_agents(str(service.config.project_path)) == []
    assert proc.poll() is None


def test_task_em_execucao_com_runtime_dono_morto_e_ceifada(
    project: Path, sleeper
) -> None:
    """Dono morto basta — a task nem precisa estar terminal."""
    service = _service(project)
    proc = sleeper()
    ident = process_identity(proc.pid)
    assert ident is not None
    task_id = _task(service, TaskState.EXECUTING)
    _register(
        service,
        task_id=task_id,
        pid=proc.pid,
        image=ident.image,
        create_time=ident.create_time,
        owner_pid=_dead_pid(),
    )

    assert proc.pid in service._reap_orphan_agents(str(service.config.project_path))
    assert _morreu(proc)


def test_limiar_de_tempo_protege_lancamento_recente(project: Path, sleeper) -> None:
    """AC-4 do enunciado: limiar configuravel na convencao dos existentes."""
    service = _service(project, reap_after_s=600)
    proc = sleeper()
    ident = process_identity(proc.pid)
    assert ident is not None
    task_id = _task(service, TaskState.COMPLETED)
    _register(
        service,
        task_id=task_id,
        pid=proc.pid,
        image=ident.image,
        create_time=ident.create_time,
        owner_pid=_dead_pid(),
        age_s=5,
    )

    assert service._reap_orphan_agents(str(service.config.project_path)) == []
    assert proc.poll() is None


def test_ceifa_e_idempotente_entre_pollers_concorrentes(
    project: Path, sleeper
) -> None:
    """AC-4 — dois processos fazendo poll no mesmo banco ceifam UMA vez."""
    primeiro = _service(project)
    segundo = build_service(project, fake_agents=True, verbose=False)
    proc = sleeper()
    ident = process_identity(proc.pid)
    assert ident is not None
    task_id = _task(primeiro, TaskState.COMPLETED)
    _register(
        primeiro,
        task_id=task_id,
        pid=proc.pid,
        image=ident.image,
        create_time=ident.create_time,
        owner_pid=_dead_pid(),
    )

    caminho = str(primeiro.config.project_path)
    a = primeiro._reap_orphan_agents(caminho)
    b = segundo._reap_orphan_agents(caminho)
    c = primeiro._reap_orphan_agents(caminho)

    assert a == [proc.pid]
    assert b == []
    assert c == []
    assert _morreu(proc)


def test_poll_de_status_dispara_a_ceifa(project: Path, sleeper) -> None:
    """Acionada pelos pontos de poll que ja existem — sem daemon, sem thread."""
    service = _service(project)
    proc = sleeper()
    ident = process_identity(proc.pid)
    assert ident is not None
    task_id = _task(service, TaskState.COMPLETED)
    _register(
        service,
        task_id=task_id,
        pid=proc.pid,
        image=ident.image,
        create_time=ident.create_time,
        owner_pid=_dead_pid(),
    )

    service.status(task_id)

    assert _morreu(proc), "o poll de status nao ceifou o orfao"


# --------------------------------------------------- registro no lancamento


def test_lancamento_persiste_identidade_e_saida_fecha_o_registro(
    project: Path,
) -> None:
    """Sem persistir a identidade no lancamento nao ha o que ceifar depois."""
    service = _service(project)
    task_id = _task(service, TaskState.EXECUTING)
    executor = CliExecutor(project, echo=False)
    service._register_process_tracking(executor, task_id, role="executor", agent="codex")

    result = executor.run(
        [sys.executable, "-c", "print('ok')"], timeout_s=60
    )
    assert result.exit_code == 0

    linhas = service.repo.list_agent_processes(str(project))
    assert len(linhas) == 1
    linha = linhas[0]
    assert linha["task_id"] == task_id
    assert linha["pid"] > 0
    assert linha["image"]
    assert linha["create_time"] > 0
    assert linha["owner_pid"] == os.getpid()
    assert linha["finished_at"], "saida do processo tem que fechar o registro"

    # Registro fechado nunca e candidato a ceifa.
    assert service._reap_orphan_agents(str(project)) == []


def test_kill_active_no_cancelamento_segue_funcionando(project: Path, sleeper) -> None:
    """AC-5 — nenhuma regressao no caminho ordenado de cancelamento."""
    executor = CliExecutor(project, echo=False)
    proc = sleeper()
    executor._active_pids.add(proc.pid)

    mortos = executor.kill_active()

    assert mortos == [proc.pid]
    assert _morreu(proc)


def test_reaper_nao_cria_daemon_nem_thread(project: Path) -> None:
    """AC-6 — a ceifa e sincrona nos polls; nada de vigia proprio."""
    fonte = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "orchestrator_runtime"
        / "agents"
        / "reaper.py"
    ).read_text(encoding="utf-8")
    assert "Thread(" not in fonte
    assert "Timer(" not in fonte
    assert "while True" not in fonte
