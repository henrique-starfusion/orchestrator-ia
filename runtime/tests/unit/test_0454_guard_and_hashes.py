"""0.4.52 — bug-078 (falso fechamento) + C1 (cap commits) + C2 (hashes).

bug-078: task C da rodada GuardLine teve executor E corrector codex falhando
    exit 1 com changed=[] e a iteração SEGUIA para validação — o juiz LLM
    aprovou 1.0 confundindo o diff de outra task no mesmo arquivo. Zero
    código entregue, fechamento falso. Agora failed + sem changed_files
    (mesmo após fallback git) é infra-reject, nunca mérito a validar.
C1: cap de 3 commits por iteração no prompt do executor (prompts.md Rule 17)
    e orientação non-blocking sobre >3 commits no prompt do validador.
C2: input_hashes (sha256 por arquivo + rev-parse HEAD) no payload da
    validation_round — re-auditoria futura reproduz o estado medido.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService, _collect_input_hashes
from orchestrator_runtime.tasks.state_machine import TaskState


# ------------------------------------------------------------------ bug-078

class _FailNoOutputAdapter(FakeAgentAdapter):
    """Executor que morre exit 1 sem produzir nada (o codex da task C)."""

    async def continue_session(self, session, request):
        if request.role in {"executor", "corrector"}:
            return AgentResult(
                session_id=session.id,
                agent_id=self.id,
                role=request.role,
                status="failed",
                exit_code=1,
                stdout="",
                stderr="crash simulado",
                command=["fake", self.id, request.role],
                cwd=str(self.project_path),
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        return await super().continue_session(session, request)


def test_failed_sem_output_nao_vai_para_validacao(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex"):
        service.registry._adapters[name] = _FailNoOutputAdapter(name, project)

    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=2,
    )
    done = asyncio.run(service.run_task(task.id))
    assert done.status != TaskState.COMPLETED, (
        "failed sem output não pode completar: era o falso fechamento da task C"
    )
    db = project / ".orchestrator" / "data" / "orchestrator.db"
    import sqlite3

    conn = sqlite3.connect(str(db))
    rounds = conn.execute(
        "select payload_json from validation_rounds where task_id=?", (task.id,)
    ).fetchall()
    conn.close()
    for (payload,) in rounds:
        p = json.loads(payload)
        assert p.get("status") != "approved" or float(p.get("score") or 0) < 0.9, (
            f"validador não pode aprovar iteração de agente falho: {p.get('status')} {p.get('score')}"
        )


# ------------------------------------------------------------------ C1

def test_prompt_executor_traz_cap_de_commits(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("qualquer 0454")
    prompt = service._build_executor_prompt(task, {}, [], test_results=None)
    assert "Cap de commits" in prompt
    assert "3 commits" in prompt
    assert "MESMA branch" in prompt


def test_prompt_validador_orienta_cap_nao_bloqueante(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("qualquer 0454")
    prompt = service._build_validator_prompt(
        task, {"status": "approved", "score": 1.0, "blocking_issues": []}, [], []
    )
    assert "3 commits novos" in prompt
    assert "non-blocking" in prompt
    assert "não reprove só por isso" in prompt


# ------------------------------------------------------------------ C2

def test_collect_input_hashes_arquivos(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print('a')\n", encoding="utf-8")
    (tmp_path / "grande.bin").write_bytes(b"x" * (3 * 1024 * 1024))
    out = _collect_input_hashes(tmp_path, ["a.py", "grande.bin", "ausente.py"])
    assert "a.py" in out["files"]
    assert len(out["files"]["a.py"]) == 64
    assert "grande.bin" not in out["files"]
    assert "ausente.py" not in out["files"]


def test_collect_input_hashes_rev_parse(tmp_path: Path) -> None:
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git ausente no ambiente de teste")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=tmp_path,
        check=True,
    )
    out = _collect_input_hashes(tmp_path, ["a.py"])
    assert len(out.get("head", "")) == 40


def test_collect_input_hashes_tolerante_sem_git(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    out = _collect_input_hashes(tmp_path, ["a.py"])
    assert "a.py" in out["files"]  # head ausente ou não, nunca quebra
