"""0.4.63 — bug-090 (deadlock de pipe), reaper de execucao presa e auto-reparo.

O deadlock era a causa raiz: com o prompt grande indo por stdin
(base_adapters.ARGV_LIMIT), o pai escrevia stdin ANTES de subir as leitoras.
Pai enche o buffer de entrada (~64KB no Windows) e espera o filho consumir; o
filho enche o de saida e espera alguem ler. Como `proc.wait(timeout=...)` so vem
depois, NENHUM timeout se aplicava — nem o do papel, nem o watchdog de silencio
da 0.4.60 — e a task ficava eterna segurando o workspace.write.lock.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentRequest, AgentResult
from orchestrator_runtime.agents.health import auth_hint, classify_agent_failure
from orchestrator_runtime.agents.process import CliExecutor
from orchestrator_runtime.tasks import service as service_module
from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState

# Escreve sem parar e NUNCA le stdin: o lado do filho do deadlock.
# Linhas TERMINADAS: `_reader` itera por linha, e um bloco sem '\n' faria o
# readline rescanear um buffer crescente (quadratico) — custo do teste, nao do
# runtime; CLI de verdade quebra linha.
_SPEWER = (
    "import sys, time\n"
    "block = 'x' * 4095 + '\\n'\n"
    "while True:\n"
    "    sys.stdout.write(block)\n"
    "    sys.stdout.flush()\n"
    "    time.sleep(0.02)\n"
)


def _run_off_thread(executor: CliExecutor, **kwargs):
    """Roda em thread separada para que 'pendurou' vire falha, nao suite travada."""
    box: dict = {}

    def go() -> None:
        box["result"] = executor.run(**kwargs)

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    thread.join(90)
    return thread, box


# --------------------------------------------------------------------------
# bug-090
# --------------------------------------------------------------------------


def test_stdin_grande_com_filho_falante_respeita_o_timeout(project: Path) -> None:
    """Prompt > 128KB por stdin + filho que so escreve: tem que sair por timeout.

    Antes do fix isto pendurava para sempre — foi o estado da task 2ffb76eb16df,
    parada 40+ min entre skill_selector e planner sem o timeout de 900s disparar.
    """
    executor = CliExecutor(project, echo=False, heartbeat_s=0)
    thread, box = _run_off_thread(
        executor,
        command=[sys.executable, "-u", "-c", _SPEWER],
        timeout_s=6,
        stdin_text="y" * 200_000,
    )

    assert not thread.is_alive(), "deadlock de pipe (bug-090): run() nunca retornou"
    result = box["result"]
    assert result.timed_out, "o timeout precisa ser quem encerra"
    assert result.stdout, "as leitoras tem que ter drenado stdout durante a escrita"


def test_stdin_continua_chegando_ao_filho(project: Path) -> None:
    """Caminho normal intacto: escrever em thread nao pode perder o texto."""
    reader = (
        "import sys\n"
        "data = sys.stdin.read()\n"
        "sys.stdout.write('recebido:%d' % len(data))\n"
    )
    executor = CliExecutor(project, echo=False, heartbeat_s=0)
    thread, box = _run_off_thread(
        executor,
        command=[sys.executable, "-u", "-c", reader],
        timeout_s=30,
        stdin_text="hello",
    )

    assert not thread.is_alive()
    result = box["result"]
    assert not result.timed_out
    assert "recebido:5" in result.stdout, "o CLI so trabalha ao ver EOF do stdin"


def test_npm_prefix_captura_em_arquivo_nunca_pipe(monkeypatch) -> None:
    """bug-B — `capture_output=True` + timeout pendura no Windows (bug-059)."""
    import subprocess

    from orchestrator_runtime.agents import process as process_module

    seen: dict = {}
    real_popen = subprocess.Popen

    def spy(cmd, **kwargs):
        seen["stdout_is_pipe"] = kwargs.get("stdout") == subprocess.PIPE
        return real_popen(cmd, **kwargs)

    monkeypatch.setattr(process_module.subprocess, "Popen", spy)
    code, out = process_module.run_capture_file(
        [sys.executable, "-c", "print('ok')"], timeout_s=30
    )

    assert code == 0
    assert "ok" in out
    assert seen["stdout_is_pipe"] is False


def test_redact_nao_e_quadratico_em_linha_longa() -> None:
    """bug-092 — descoberto ao escrever o teste do bug-090.

    `[\\w.\\-\\[\\]]*` antes da alternação fazia o regex consumir a linha inteira
    em CADA posição inicial e voltar um char por vez: 2,4 MB de saída de agente
    (linhas de 4 KB) queimavam ~100 s de CPU só redigindo. E `redact()` roda no
    fim de toda execução — e a cada linha quando o echo está ligado.
    """
    import time

    from orchestrator_runtime.agents.process import redact

    payload = "\n".join("x" * 4095 for _ in range(200))
    start = time.monotonic()
    out = redact(payload)
    elapsed = time.monotonic() - start

    assert out == payload, "linha sem segredo tem que sair intacta"
    assert elapsed < 2.0, f"redact quadratico: {elapsed:.1f}s em 800KB sem segredo"


def test_redact_ainda_esconde_o_segredo() -> None:
    from orchestrator_runtime.agents.process import redact

    assert "supersecret" not in redact("API_KEY=supersecret")
    assert "prosa sobre token de acesso" in redact("prosa sobre token de acesso")


def test_run_capture_file_devolve_no_timeout() -> None:
    """Com arquivo em vez de PIPE, o pos-kill nao espera neto nenhum."""
    from orchestrator_runtime.agents.process import run_capture_file

    code, out = run_capture_file(
        [sys.executable, "-c", "import time; time.sleep(30)"], timeout_s=3
    )
    assert code == 124
    assert "timeout" in out


# --------------------------------------------------------------------------
# reaper de task nao-terminal
# --------------------------------------------------------------------------


def _age_task(svc, task_id: str, *, seconds: int) -> None:
    """Envelhece `updated_at` no DB (a API publica sempre grava 'agora')."""
    from orchestrator_runtime.tasks.repository import TaskRow

    stamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=seconds)
    with svc.repo.session() as s:
        row = s.get(TaskRow, task_id)
        row.updated_at = stamp
        s.commit()


def _force_state(svc, task_id: str, state: TaskState) -> None:
    from orchestrator_runtime.tasks.repository import TaskRow

    with svc.repo.session() as s:
        row = s.get(TaskRow, task_id)
        row.status = state.value
        s.commit()


def test_execucao_velha_sem_dono_e_cancelada_e_libera_a_fila(project: Path) -> None:
    """Foi a ausencia disto que custou ~11h de fila parada no printbee."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task que travou em EXECUTING")
    _force_state(svc, task.id, TaskState.EXECUTING)
    _age_task(svc, task.id, seconds=6 * 3600)

    assert svc._busy_task_id(str(project)) == task.id, "pre-condicao: fila barrada"

    assert svc._cancel_stale_execution() == 1
    assert svc.get(task.id).status == TaskState.CANCELLED
    assert svc._busy_task_id(str(project)) is None, "a fila tem que destravar"


def test_execucao_recente_nao_e_tocada(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task trabalhando agora")
    _force_state(svc, task.id, TaskState.EXECUTING)

    assert svc._cancel_stale_execution() == 0
    assert svc.get(task.id).status == TaskState.EXECUTING


def test_task_deste_processo_nunca_e_ceifada(project: Path) -> None:
    """Quem esta em _running_tasks tem coroutine viva aqui — por definicao."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("rodando neste processo")
    _force_state(svc, task.id, TaskState.EXECUTING)
    _age_task(svc, task.id, seconds=6 * 3600)
    svc._running_tasks.add(task.id)

    assert svc._cancel_stale_execution() == 0
    assert svc.get(task.id).status == TaskState.EXECUTING


def test_queued_velha_nao_e_ceifada(project: Path) -> None:
    """Esperar na fila E o trabalho dela; quem destrava e o cancel de quem esta na frente."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("esperando na fila")
    _force_state(svc, task.id, TaskState.QUEUED)
    _age_task(svc, task.id, seconds=6 * 3600)

    assert svc._cancel_stale_execution() == 0
    assert svc.get(task.id).status == TaskState.QUEUED


def test_status_e_list_disparam_o_reaper(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("zumbi visto por quem faz polling")
    _force_state(svc, task.id, TaskState.EXECUTING)
    _age_task(svc, task.id, seconds=6 * 3600)

    assert svc.status(task.id)["status"] == TaskState.CANCELLED.value


def test_grace_zero_desliga_o_reaper(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    svc.config.limits.stale_execution_grace_s = 0
    task = svc.create_task("reaper desligado")
    _force_state(svc, task.id, TaskState.EXECUTING)
    _age_task(svc, task.id, seconds=6 * 3600)

    assert svc._cancel_stale_execution() == 0


# --------------------------------------------------------------------------
# classificacao de CLI quebrado
# --------------------------------------------------------------------------


def _result(**kw) -> AgentResult:
    base = dict(
        session_id="s",
        agent_id="codex",
        role="executor",
        status="failed",
        exit_code=1,
        stdout="",
        stderr="",
        duration_s=2.0,
    )
    base.update(kw)
    return AgentResult(**base)


def test_cli_ausente_classifica_install() -> None:
    assert classify_agent_failure(
        _result(stderr="'codex' is not recognized as an internal or external command")
    ) == "install"


def test_npm_error_classifica_install() -> None:
    assert classify_agent_failure(_result(stderr="npm error code EBUSY")) == "install"


def test_falta_de_credencial_classifica_auth_e_nao_install() -> None:
    """auth vence install: reinstalar apaga a sessao e nao conserta nada."""
    res = _result(stderr="npm error\nYou are not logged in. Run `codex login`.")
    assert classify_agent_failure(res) == "auth"


def test_timeout_nunca_e_cli_quebrado() -> None:
    """Quem passou do tempo estava vivo; esse caminho tem dono em _timeout_issue."""
    assert (
        classify_agent_failure(
            _result(timed_out=True, stderr="command not found", duration_s=2400.0)
        )
        is None
    )


def test_sucesso_nunca_e_classificado() -> None:
    assert classify_agent_failure(_result(status="completed", stderr="npm error")) is None


def test_corrector_da_guardline_nao_e_cli_quebrado() -> None:
    """Caso negativo real (e0457603df65): 17 min, 20KB de stderr, exit=1.

    Sem marcador e com duracao longa isso e MERITO — reinstalar seria queimar
    orcamento por causa de um agente que trabalhou de verdade.
    """
    res = _result(stdout="", stderr="E" * 20_000, duration_s=17 * 60)
    assert classify_agent_failure(res) is None


def test_morte_muda_e_rapida_classifica_install() -> None:
    """codex/opencode: exit=1, zero byte, poucos segundos."""
    assert classify_agent_failure(_result(stdout="", stderr="", duration_s=1.5)) == "install"


def test_auth_hint_conhecido_e_generico() -> None:
    assert auth_hint("codex") == "codex login"
    assert "desconhecido" in auth_hint("desconhecido")


# --------------------------------------------------------------------------
# reparo (sem npm, sem powershell, sem rede)
# --------------------------------------------------------------------------


def test_repair_sem_powershell_nao_explode(monkeypatch) -> None:
    from orchestrator_runtime.agents import repair as repair_module

    monkeypatch.setattr(repair_module, "find_powershell", lambda: None)
    out = repair_module.repair_agent("codex", project_path=Path("."))

    assert out.ok is False
    assert out.available is False
    assert out.summary == "reparo indisponível"


def test_repair_chama_update_agents_com_only_e_force(monkeypatch, tmp_path: Path) -> None:
    from orchestrator_runtime.agents import repair as repair_module

    script = tmp_path / "scripts" / "Update-Agents.ps1"
    script.parent.mkdir(parents=True)
    script.write_text("# fake", encoding="utf-8")

    seen: dict = {}

    def fake_run(command, *, cwd=None, timeout_s=60, env=None):
        seen["command"] = list(command)
        return 0, "updated"

    monkeypatch.setattr(repair_module, "find_powershell", lambda: "powershell.exe")
    monkeypatch.setattr(repair_module, "update_agents_script", lambda: script)
    monkeypatch.setattr(repair_module, "run_capture_file", fake_run)

    out = repair_module.repair_agent("codex", project_path=tmp_path, timeout_s=90)

    assert out.ok is True
    cmd = seen["command"]
    assert cmd[:2] == ["powershell.exe", "-NoProfile"]
    assert cmd[cmd.index("-Only") + 1] == "codex"
    assert "-Force" in cmd, "sem -Force os fallbacks npm/choco nao disparam"


# --------------------------------------------------------------------------
# fio do runtime: reparar e reexecutar UMA vez
# --------------------------------------------------------------------------


class _Adapter:
    def __init__(self, results: list[AgentResult]) -> None:
        self._results = results
        self.calls = 0

    async def run(self, request: AgentRequest) -> AgentResult:
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


@pytest.mark.asyncio
async def test_install_repara_e_reexecuta_uma_vez(project: Path, monkeypatch) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("agente com CLI quebrado")
    broken = _result(stderr="npm error code EBUSY")
    fixed = _result(status="completed", exit_code=0, stdout="feito")
    # `broken` já é o resultado da 1ª execução (feita pelo chamador); o adapter
    # só é chamado de novo DEPOIS do reparo.
    adapter = _Adapter([fixed])
    request = AgentRequest(role="executor", prompt="p", cwd=str(project))

    repairs: list[str] = []

    def fake_repair(agent_id, *, project_path, timeout_s):
        from orchestrator_runtime.agents.repair import RepairResult

        repairs.append(agent_id)
        return RepairResult(True, f"{agent_id}: reinstalação concluída")

    monkeypatch.setattr(service_module, "repair_agent", fake_repair)

    out = await svc._maybe_repair_and_retry(
        adapter, request, broken, task=task, role="executor", agent_id="codex"
    )

    assert out.status == "completed"
    assert adapter.calls == 1, "a reexecucao acontece dentro do helper"
    assert repairs == ["codex"]

    # Segunda falha do MESMO agente nao repara de novo.
    out2 = await svc._maybe_repair_and_retry(
        adapter, request, broken, task=task, role="executor", agent_id="codex"
    )
    assert repairs == ["codex"], "um reparo por agente por processo"
    assert out2 is broken


@pytest.mark.asyncio
async def test_auth_nao_reinstala(project: Path, monkeypatch) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("agente deslogado")
    res = _result(stderr="You are not logged in. Run `codex login`.")
    adapter = _Adapter([res])
    request = AgentRequest(role="executor", prompt="p", cwd=str(project))

    called: list[str] = []
    monkeypatch.setattr(
        service_module,
        "repair_agent",
        lambda *a, **k: called.append("x"),  # noqa: ARG005
    )

    out = await svc._maybe_repair_and_retry(
        adapter, request, res, task=task, role="executor", agent_id="codex"
    )

    assert out is res
    assert called == [], "reinstalar um CLI deslogado apaga a sessao e nao resolve"
    hints = [
        e for e in svc.repo.list_events(task.id) if (e.get("data") or {}).get("auth_command")
    ]
    assert hints and hints[-1]["data"]["auth_command"] == "codex login"


@pytest.mark.asyncio
async def test_auto_repair_desligado_nao_repara(project: Path, monkeypatch) -> None:
    svc = build_service(project, fake_agents=True)
    svc.config.limits.agent_auto_repair = False
    task = svc.create_task("auto-reparo desligado")
    broken = _result(stderr="npm error code EBUSY")
    adapter = _Adapter([broken])
    request = AgentRequest(role="executor", prompt="p", cwd=str(project))

    called: list[str] = []
    monkeypatch.setattr(
        service_module, "repair_agent", lambda *a, **k: called.append("x")  # noqa: ARG005
    )

    out = await svc._maybe_repair_and_retry(
        adapter, request, broken, task=task, role="executor", agent_id="codex"
    )

    assert out is broken
    assert called == []
