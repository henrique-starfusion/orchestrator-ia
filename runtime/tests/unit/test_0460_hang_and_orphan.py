"""0.4.60 — watchdog de silêncio, adoção de órfã e rótulo honesto de timeout.

Casos vindos de duas tasks reais de 2026-08-06:
- GuardLine e0457603df65: executor 40 min com ZERO byte; corrector que estava
  produzindo morto pelo teto da task; erro final rotulado "NO-OUTPUT" para quem
  tinha 20KB de stderr (bug-086 + bug-087).
- trustsafe c4b7a1d12d6b: RECEIVED por 30 min com o workspace livre e nenhuma
  outra task — ninguém adotava (bug-085).
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator_runtime.agents.process import NO_OUTPUT_MARKER, CliExecutor
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState


# --------------------------------------------------------------------------
# bug-086 — watchdog de silêncio
# --------------------------------------------------------------------------


def _sleeper(seconds: int) -> list[str]:
    """Processo que fica mudo por N segundos (nem stdout nem stderr)."""
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def _talker(seconds: float, every: float = 0.2) -> list[str]:
    """Processo que fala sem parar — watchdog não pode encostar nele."""
    code = (
        "import sys,time\n"
        f"end=time.time()+{seconds}\n"
        "while time.time()<end:\n"
        f"    print('tick', flush=True); time.sleep({every})\n"
    )
    return [sys.executable, "-c", code]


def test_watchdog_mata_agente_mudo(tmp_path: Path) -> None:
    ex = CliExecutor(tmp_path, echo=False)
    ex.no_output_timeout_s = 2
    result = ex.run(_sleeper(60), timeout_s=120)

    assert result.timed_out is True
    assert NO_OUTPUT_MARKER in result.stderr
    # Morreu pelo watchdog (~2s), não pelo timeout_s de 120s.
    assert result.duration_s < 30


def test_watchdog_desligado_por_padrao(tmp_path: Path) -> None:
    """Sem configurar, nada muda: 0 = desligado (compatibilidade)."""
    ex = CliExecutor(tmp_path, echo=False)
    assert ex.no_output_timeout_s == 0
    result = ex.run(_sleeper(1), timeout_s=30)
    assert result.timed_out is False
    assert NO_OUTPUT_MARKER not in result.stderr


def test_watchdog_nao_mata_quem_fala(tmp_path: Path) -> None:
    ex = CliExecutor(tmp_path, echo=False)
    ex.no_output_timeout_s = 2
    result = ex.run(_talker(6), timeout_s=60)

    assert result.timed_out is False
    assert NO_OUTPUT_MARKER not in result.stderr
    assert "tick" in result.stdout


def test_watchdog_respeita_progresso_no_workspace(tmp_path: Path) -> None:
    """`claude -p` só imprime no fim: mudou arquivo, está vivo."""
    ex = CliExecutor(tmp_path, echo=False)
    ex.no_output_timeout_s = 2
    ex.progress_probe = lambda: True
    started = time.monotonic()
    result = ex.run(_sleeper(5), timeout_s=60)

    assert result.timed_out is False
    assert NO_OUTPUT_MARKER not in result.stderr
    assert time.monotonic() - started >= 4  # rodou até o fim


def test_sonda_quebrada_nunca_mata(tmp_path: Path) -> None:
    """Sem prova de morte, sem kill — git lento não pode matar agente."""

    def _boom() -> bool:
        raise RuntimeError("git indisponivel")

    ex = CliExecutor(tmp_path, echo=False)
    ex.no_output_timeout_s = 2
    ex.progress_probe = _boom
    result = ex.run(_sleeper(5), timeout_s=60)

    assert result.timed_out is False
    assert NO_OUTPUT_MARKER not in result.stderr


# --------------------------------------------------------------------------
# bug-087 — rótulo honesto
# --------------------------------------------------------------------------


def _service(tmp_path: Path) -> TaskService:
    root = tmp_path / ".orchestrator"
    (root / "config").mkdir(parents=True)
    (root / "data").mkdir(parents=True)
    config = load_config(tmp_path, fake_agents=True)
    return TaskService(config, verbose=False)


def _result(stdout: str = "", stderr: str = "", duration: float = 100.0):
    return SimpleNamespace(
        stdout=stdout, stderr=stderr, duration_s=duration, timed_out=True
    )


def _task(max_duration: int = 3600):
    return SimpleNamespace(
        id="t1", constraints=SimpleNamespace(maximum_duration_seconds=max_duration)
    )


@pytest.mark.parametrize(
    "stdout,stderr,remaining,expected",
    [
        ("", f"boom {NO_OUTPUT_MARKER} morto", 3000, "AGENT-NO-OUTPUT-HANG"),
        ("", "", 3000, "AGENT-TIMEOUT-NO-OUTPUT"),
        ("trabalhei muito", "", 3000, "AGENT-TIMEOUT-NO-CHANGES"),
        # 20KB de stderr + orçamento no fim = o caso do corrector da GuardLine
        ("", "erro real do agente", 0, "TASK-BUDGET-EXHAUSTED"),
    ],
)
def test_rotulo_por_evidencia(
    tmp_path: Path, monkeypatch, stdout: str, stderr: str, remaining: int, expected: str
) -> None:
    svc = _service(tmp_path)
    monkeypatch.setattr(svc, "_remaining_duration_s", lambda _t: remaining)
    issue_id, description, error_text = svc._timeout_issue(
        "corrector", "codex", _result(stdout, stderr), _task()
    )
    assert issue_id == expected
    assert expected in error_text
    assert "corrector/codex" in description


def test_hang_vence_orcamento(tmp_path: Path, monkeypatch) -> None:
    """Pendurado é diagnóstico mais específico que 'acabou o tempo'."""
    svc = _service(tmp_path)
    monkeypatch.setattr(svc, "_remaining_duration_s", lambda _t: 0)
    issue_id, _, _ = svc._timeout_issue(
        "executor", "claude", _result("", f"{NO_OUTPUT_MARKER} x"), _task()
    )
    assert issue_id == "AGENT-NO-OUTPUT-HANG"


# --------------------------------------------------------------------------
# bug-085 — adoção de órfã RECEIVED
# --------------------------------------------------------------------------


def _age_task(svc: TaskService, task_id: str, minutes: int) -> None:
    """Envelhece created_at direto no DB (o serviço lê a string do SQLite)."""
    old = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    from orchestrator_runtime.memory.database import TaskRow

    with svc.repo.session() as session:
        row = session.get(TaskRow, task_id)
        row.created_at = old
        session.commit()


def test_orfa_recebida_e_adotada(tmp_path: Path, monkeypatch) -> None:
    svc = _service(tmp_path)
    task = svc.create_task("documentar modulo x")
    _age_task(svc, task.id, minutes=10)

    started: list[str] = []
    monkeypatch.setattr(
        svc, "_start_background", lambda tid, name: started.append(f"{name}:{tid}")
    )
    svc._adopt_orphan_received(str(svc.config.project_path))

    assert started == [f"adopt:{task.id}"]


def test_orfa_recente_nao_e_roubada(tmp_path: Path, monkeypatch) -> None:
    """Quem acabou de criar vai chamar run_task: não atropelar."""
    svc = _service(tmp_path)
    svc.create_task("tarefa recem criada")

    started: list[str] = []
    monkeypatch.setattr(
        svc, "_start_background", lambda tid, name: started.append(tid)
    )
    svc._adopt_orphan_received(str(svc.config.project_path))

    assert started == []


def test_adocao_nao_repete_na_mesma_sessao(tmp_path: Path, monkeypatch) -> None:
    """Poll de status é constante: uma thread por órfã, não uma por poll."""
    svc = _service(tmp_path)
    task = svc.create_task("documentar modulo y")
    _age_task(svc, task.id, minutes=10)

    started: list[str] = []
    monkeypatch.setattr(
        svc, "_start_background", lambda tid, name: started.append(tid)
    )
    for _ in range(5):
        svc._adopt_orphan_received(str(svc.config.project_path))

    assert started == [task.id]


def test_status_adota(tmp_path: Path, monkeypatch) -> None:
    svc = _service(tmp_path)
    task = svc.create_task("documentar modulo z")
    _age_task(svc, task.id, minutes=10)

    started: list[str] = []
    monkeypatch.setattr(
        svc, "_start_background", lambda tid, name: started.append(tid)
    )
    out = svc.status(task.id)

    assert out["status"] == TaskState.RECEIVED.value
    assert started == [task.id]


def test_workspace_ocupado_nao_adota(tmp_path: Path, monkeypatch) -> None:
    svc = _service(tmp_path)
    task = svc.create_task("documentar modulo w")
    _age_task(svc, task.id, minutes=10)

    started: list[str] = []
    monkeypatch.setattr(
        svc, "_start_background", lambda tid, name: started.append(tid)
    )
    monkeypatch.setattr(svc, "_busy_task_id", lambda *_a, **_k: "outra-task")
    svc._adopt_orphan_received_safe(str(svc.config.project_path))

    assert started == []
