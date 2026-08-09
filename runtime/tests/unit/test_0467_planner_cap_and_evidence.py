"""0.4.67 — o teto da fase matava o planner, e ninguem ficava sabendo.

Medido no printbee (4 tasks): `planner/claude/fable` concluiu em 57s e 81s duas
vezes, e morreu em 180s CRAVADOS com ZERO byte nas outras duas. 50% de perda.

Causa: `SELECTING_AGENTS_CAP_S` era 180 — MENOR que o proprio
`PLANNER_REFINE_CAP_S` (300). Como o teto efetivo e
`min(300, 180 - decorrido)`, os 300s prometidos nunca eram alcancaveis. E o
modelo preferido do planner e `fable`, o mais deliberativo. `claude -p` so
imprime no fim, entao o kill nao deixa nem saida parcial.

Como o refino e advisory, a task seguia e terminava COMPLETED score 1.0 —
indistinguivel de uma que FOI refinada.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator_runtime.agents.process import ProcessResult
from orchestrator_runtime.testing.discovery import TestRunner
from orchestrator_runtime.tasks.service import build_service


# --------------------------------------------------------------------------
# bug-101 — o teto da fase tem que comportar o refino que ela promete
# --------------------------------------------------------------------------


def test_teto_da_fase_comporta_o_refino_inteiro(project: Path) -> None:
    svc = build_service(project, fake_agents=True)

    assert svc.selecting_agents_cap_s > svc.PLANNER_REFINE_CAP_S, (
        "teto da fase menor que o do refino: os segundos prometidos ao planner "
        "sao inalcancaveis (era 180 < 300 e matava fable aos 180s)"
    )
    esperado = svc.config.limits.skill_selection_timeout_s + svc.PLANNER_REFINE_CAP_S
    assert svc.selecting_agents_cap_s == esperado


def test_teto_acompanha_a_config_do_skill_selector(project: Path) -> None:
    """Se o skill_selector ganha mais tempo, a fase cresce junto — por construcao."""
    svc = build_service(project, fake_agents=True)
    svc.config.limits.skill_selection_timeout_s = 240

    assert svc.selecting_agents_cap_s == 240 + svc.PLANNER_REFINE_CAP_S


# --------------------------------------------------------------------------
# bug-102 — plano cru nao pode se passar por plano refinado
# --------------------------------------------------------------------------


def test_sem_falha_no_refino_status_nao_inventa_campo(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("qualquer coisa")

    out = svc.status(task.id)
    assert "plan_refined" not in out
    assert "plan_warning" not in out


def test_refino_perdido_aparece_no_status(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task cujo planner morreu no teto")

    svc._mark_plan_not_refined(task, agent="claude", detail="timeout em 180s")

    out = svc.status(task.id)
    assert out["plan_refined"] is False
    assert "plano determinístico" in out["plan_warning"]
    assert "timeout em 180s" in out["plan_warning"]


def test_refino_perdido_sobrevive_ao_processo(project: Path) -> None:
    """Evento sozinho some do status; tem que estar persistido em `analysis`."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("persistencia do aviso")
    svc._mark_plan_not_refined(task, agent="claude", detail="timeout em 180s")

    outro = build_service(project, fake_agents=True)
    assert outro.status(task.id)["plan_refined"] is False


def test_marcar_refino_perdido_nunca_derruba_a_task(project: Path) -> None:
    svc = build_service(project, fake_agents=True)

    # Task inexistente: a observabilidade falha em silencio, sem excecao.
    class _Fake:
        id = "nao-existe"
        analysis: dict = {}

    svc._mark_plan_not_refined(_Fake(), agent="claude", detail="x")


# --------------------------------------------------------------------------
# bug-100 — pytest exit 5 = "nenhum teste coletado", nao regressao
# --------------------------------------------------------------------------


class _FakeProcExecutor:
    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code

    def run(self, command, *, cwd=None, timeout_s=600, env=None,
            heartbeat_s=None, allow_nested=False, stdin_text=None):
        return ProcessResult(
            exit_code=self.exit_code,
            stdout="no tests ran",
            stderr="",
            timed_out=False,
            duration_s=0.01,
            command=list(command),
            cwd=str(cwd or ""),
        )


def _pytest_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(
        "orchestrator_runtime.testing.discovery.which", lambda name: f"/fake/{name}"
    )


def test_pytest_sem_teste_coletado_nao_e_falha(tmp_path, monkeypatch) -> None:
    """printbee e .NET + Angular; `pytest -q` saia 5 em TODA task e virava
    `failed/introduced` — a task era cobrada por nao ter quebrado nada."""
    _pytest_project(tmp_path, monkeypatch)
    resultados = TestRunner(_FakeProcExecutor(5)).run_all(tmp_path)

    pytest_runs = [r for r in resultados if "pytest" in r["command"]]
    assert pytest_runs, "o cenario precisa de pelo menos um comando pytest"
    for r in pytest_runs:
        assert r["status"] == "skipped", f"exit 5 virou {r['status']}"
        assert r["failure_kind"] == "no_tests_collected"


def test_pytest_com_falha_de_verdade_continua_falha(tmp_path, monkeypatch) -> None:
    """O caso legitimo nao pode ser perdido junto: exit 1 e teste vermelho."""
    _pytest_project(tmp_path, monkeypatch)
    resultados = TestRunner(_FakeProcExecutor(1)).run_all(tmp_path)

    pytest_runs = [r for r in resultados if "pytest" in r["command"]]
    assert pytest_runs
    for r in pytest_runs:
        assert r["status"] == "failed"
        assert r["failure_kind"] == "introduced"


def test_exit_5_de_outro_comando_nao_e_perdoado(tmp_path, monkeypatch) -> None:
    """A regra e do pytest: 5 so significa 'sem teste coletado' nele."""
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8"
    )
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(
        "orchestrator_runtime.testing.discovery.which", lambda name: f"/fake/{name}"
    )
    resultados = TestRunner(_FakeProcExecutor(5)).run_all(tmp_path)

    npm_runs = [r for r in resultados if r["command"].startswith("npm")]
    assert npm_runs
    for r in npm_runs:
        assert r["status"] == "failed"
        assert r["failure_kind"] == "introduced"
