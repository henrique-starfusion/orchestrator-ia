from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from orchestrator_runtime.mcp.tools import OrchestratorMcpTools


PROMPT = (
    "Auditoria e correção: botões HTML sem atributo type no frontend. "
    "Validar ação, paginação e não regressão."
)


def _run_runtime(project: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "runtime" / "src")
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run(
        [sys.executable, "-m", "orchestrator_runtime", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
    )


def test_windows_cli_preserves_pt_br_through_db_mcp_and_output(project: Path) -> None:
    created = _run_runtime(
        project,
        "task",
        "create",
        "--prompt",
        PROMPT,
        "--project",
        str(project),
        "--fake-agents",
        "--json",
    )
    assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")
    created_payload = json.loads(created.stdout.decode("utf-8"))
    task_id = created_payload["id"]
    assert created_payload["prompt"] == PROMPT

    db_path = project / ".orchestrator" / "data" / "orchestrator.db"
    with sqlite3.connect(db_path) as connection:
        stored_prompt = connection.execute(
            "SELECT prompt FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()[0]
    assert stored_prompt == PROMPT

    tools = OrchestratorMcpTools(
        default_workspace=project, fake_agents=True, verbose=False
    )
    assert tools.result({"task_id": task_id})["summary"] == PROMPT

    json_list = _run_runtime(
        project,
        "task",
        "list",
        "--project",
        str(project),
        "--json",
    )
    assert json_list.returncode == 0
    listed_payload = json.loads(json_list.stdout.decode("utf-8"))
    assert listed_payload[0]["prompt"] == PROMPT

    text_list = _run_runtime(
        project,
        "task",
        "list",
        "--project",
        str(project),
    )
    assert text_list.returncode == 0
    rendered = text_list.stdout.decode("utf-8")
    assert "correção" in rendered
    assert "botões" in rendered
    assert "frontend…" in rendered
    assert "corre��o" not in rendered
    assert "correo" not in rendered
