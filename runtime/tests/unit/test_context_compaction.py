"""0.4.14: learn-then-compact context — digest, durable learning, retrieval."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator_runtime.config import RuntimeLimits, load_config
from orchestrator_runtime.memory import learnings as L
from orchestrator_runtime.mcp.tools import OrchestratorMcpTools
from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    CriterionKind,
    TaskRecord,
)
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState


# ------------------------------------------------------------------ helpers


def _service(project: Path) -> TaskService:
    config = load_config(project, fake_agents=True)
    return TaskService(config, verbose=False)


def _task(project: Path, prompt: str = "Implemente feature digest 0.4.14") -> TaskRecord:
    return TaskRecord(
        prompt=prompt,
        project_path=str(project),
        task_type="implementation",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Feature presente",
                kind=CriterionKind.WORKSPACE_CHANGES,
            )
        ],
    )


class _Task:
    """Minimal stand-in for extract_learning / build_digest unit tests."""

    def __init__(self, **kw):
        self.id = kw.get("id", "abc123")
        self.prompt = kw.get("prompt", "obj")
        self.task_type = kw.get("task_type", "implementation")
        self.last_score = kw.get("last_score", 0.95)
        self.plan = kw.get("plan", {"strategy": "pair", "roles": {"executor": "claude"}})
        self.analysis = kw.get("analysis", {"selected_skills": ["skill-a"]})
        self.documentation_review = kw.get("documentation_review", {})

        class _S:
            value = kw.get("status", "COMPLETED")

        self.status = _S()


# ------------------------------------------------------------------ module: extract/digest


def test_extract_learning_captures_run_context():
    task = _Task()
    run_ctx = {
        "changed_files": ["a.py", "b.py"],
        "test_results": [{"command": "npm test", "status": "passed"}],
        "last_validation": {
            "blocking_issues": [{"id": "X1", "description": "boom"}]
        },
    }
    learning = L.extract_learning(task, success=True, strategy="pair", run_ctx=run_ctx)
    assert learning["files_touched"] == ["a.py", "b.py"]
    assert learning["tests"] == [{"command": "npm test", "status": "passed"}]
    assert learning["blockers"] == ["X1: boom"]
    assert learning["skills_used"] == ["skill-a"]
    assert learning["strategy"] == "pair"


def test_build_digest_respects_max_chars():
    task = _Task(prompt="P" * 5000)
    learning = L.extract_learning(task, success=False, run_ctx={})
    digest = L.build_digest(learning, max_chars=120)
    assert len(digest) <= 120
    assert digest.endswith("[TRUNCATED]")


def test_build_digest_contains_key_fields():
    task = _Task()
    learning = L.extract_learning(
        task, success=True, strategy="pair",
        run_ctx={"changed_files": ["x.py"]},
    )
    digest = L.build_digest(learning)
    assert "task_id: abc123" in digest
    assert "learning_path: .orchestrator/memory/learnings/abc123.md" in digest
    assert "x.py" in digest


def test_memory_content_is_keyword_rich():
    task = _Task(prompt="objetivo unico xyzzy")
    learning = L.extract_learning(task, success=True, run_ctx={})
    content = L.memory_content(learning)
    assert "xyzzy" in content
    assert "learning" in content


# ------------------------------------------------------------------ module: artifacts/index/wolf


def test_compact_result_artifacts_truncates_big_files(tmp_path: Path):
    results = tmp_path / "results" / "t1"
    results.mkdir(parents=True)
    big = results / "executor-claude.txt"
    big.write_text("Z" * 50000, encoding="utf-8")
    small = results / "validator-codex.txt"
    small.write_text("ok", encoding="utf-8")
    compacted = L.compact_result_artifacts(results, max_chars=20000)
    assert "executor-claude.txt" in compacted
    assert "validator-codex.txt" not in compacted
    text = big.read_text(encoding="utf-8")
    assert len(text) <= 20000
    assert text.endswith("[TRUNCATED]")


def test_update_index_dedupes_by_task(tmp_path: Path):
    task = _Task(id="dup1")
    learning = L.extract_learning(task, success=True, run_ctx={})
    digest = L.build_digest(learning)
    L.update_index(tmp_path, learning, digest)
    L.update_index(tmp_path, learning, digest)
    data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    ids = [e["task_id"] for e in data["learnings"]]
    assert ids.count("dup1") == 1


def test_update_wolf_status_idempotent_block(tmp_path: Path):
    wolf = tmp_path / ".wolf"
    wolf.mkdir()
    (wolf / "STATUS.md").write_text("# STATUS\n\nbody\n", encoding="utf-8")
    task = _Task(id="w1", prompt="first objective")
    L.update_wolf_status(wolf, L.extract_learning(task, success=True, run_ctx={}))
    task2 = _Task(id="w1", prompt="second objective")
    L.update_wolf_status(wolf, L.extract_learning(task2, success=True, run_ctx={}))
    text = (wolf / "STATUS.md").read_text(encoding="utf-8")
    assert text.count("Last orchestrator task") == 1
    assert "w1" in text


def test_append_cerebrum_pitfall_only_on_failure(tmp_path: Path):
    wolf = tmp_path / ".wolf"
    wolf.mkdir()
    (wolf / "cerebrum.md").write_text("# Cerebrum\n\n## Do-Not-Repeat\n\n", encoding="utf-8")
    ok = _Task(id="ok1", status="COMPLETED")
    L.append_cerebrum_pitfall(wolf, L.extract_learning(ok, success=True, run_ctx={}))
    assert "ok1" not in (wolf / "cerebrum.md").read_text(encoding="utf-8")
    bad = _Task(id="bad1", status="INCOMPLETE")
    learning = L.extract_learning(
        bad, success=False,
        run_ctx={"last_validation": {"blocking_issues": [{"id": "B", "description": "d"}]}},
    )
    L.append_cerebrum_pitfall(wolf, learning)
    assert "bad1" in (wolf / "cerebrum.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ service: order + persistence


def test_learning_saved_before_compaction(project: Path, monkeypatch):
    """Ordem obrigatória: learning em disco ANTES da compactação de artefatos."""
    svc = _service(project)
    task = _task(project)
    svc.repo.create(task)
    task.status = TaskState.COMPLETED
    svc.repo.save(task)
    svc._run_ctx = {"changed_files": ["z.py"], "test_results": [], "last_validation": {}}

    results = svc.config.orchestrator_root / "runtime" / "results" / task.id
    results.mkdir(parents=True, exist_ok=True)
    (results / "executor-claude.txt").write_text("Q" * 40000, encoding="utf-8")

    seen: dict[str, bool] = {}
    orig = L.compact_result_artifacts

    def _spy(results_dir, **kw):
        rows = svc.repo.search_memories(task.prompt, kind="learning")
        seen["learning_first"] = len(rows) > 0
        return orig(results_dir, **kw)

    monkeypatch.setattr(L, "compact_result_artifacts", _spy)
    svc._persist_episode(task, success=True, strategy="pair")

    assert seen.get("learning_first") is True
    # learning file + index written
    assert (
        svc.config.orchestrator_root / "memory" / "learnings" / f"{task.id}.md"
    ).is_file()
    assert (svc.config.orchestrator_root / "memory" / "index.json").is_file()
    # artifact compacted after
    art = (results / "executor-claude.txt").read_text(encoding="utf-8")
    assert len(art) <= 20000 and art.endswith("[TRUNCATED]")


def test_digest_present_in_result(project: Path):
    tools = OrchestratorMcpTools(default_workspace=project, fake_agents=True, verbose=False)
    service = tools._service()
    task = service.create_task("Implemente feature de digest e memoria")
    task.status = TaskState.COMPLETED
    service.repo.save(task)
    service._run_ctx = {"changed_files": ["m.py"], "test_results": [], "last_validation": {}}
    service._persist_episode(task, success=True, strategy="pair")

    res = tools.result({"task_id": task.id})
    assert res["session_digest"]
    assert res["memory"]["learning_saved"] is True
    assert res["memory"]["learning_path"].endswith(f"{task.id}.md")
    assert res["context_compaction"]["learning_path"].endswith(f"{task.id}.md")


def test_retrieval_includes_learning(project: Path):
    svc = _service(project)
    task = _task(project, prompt="objetivo raro zephyrxx")
    svc.repo.create(task)
    task.status = TaskState.COMPLETED
    svc.repo.save(task)
    svc._run_ctx = {"changed_files": [], "test_results": [], "last_validation": {}}
    svc._persist_episode(task, success=True, strategy="pair")

    learnings = svc.repo.search_memories("zephyrxx", kind="learning")
    assert learnings, "learning deve ser recuperável por kind=learning"
    assert learnings[0]["kind"] == "learning"
    # injeção no prompt do executor
    block = svc._learnings_block(learnings)
    assert "Aprendizados de tarefas anteriores" in block
    prompt = svc._build_executor_prompt(task, {}, [], learnings=learnings)
    assert "Aprendizados de tarefas anteriores" in prompt


# ------------------------------------------------------------------ config


def test_runtime_limits_context_compaction_defaults():
    limits = RuntimeLimits()
    assert limits.context_compaction_enabled is True
    assert limits.save_learning_before_compact is True
    assert limits.digest_max_chars == 1500
    assert limits.truncate_result_artifacts_chars == 20000
    assert limits.update_wolf_status is True


def test_load_config_reads_context_compaction(project: Path):
    policies_path = project / ".orchestrator" / "config" / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["context_compaction"] = {
        "enabled": False,
        "save_learning_before_compact": False,
        "digest_max_chars": 800,
        "truncate_result_artifacts_chars": 5000,
        "update_wolf_status": False,
    }
    policies_path.write_text(json.dumps(policies), encoding="utf-8")
    config = load_config(project)
    assert config.limits.context_compaction_enabled is False
    assert config.limits.save_learning_before_compact is False
    assert config.limits.digest_max_chars == 800
    assert config.limits.truncate_result_artifacts_chars == 5000
    assert config.limits.update_wolf_status is False


def test_live_policies_has_context_compaction_block():
    repo_root = Path(__file__).resolve().parents[3]
    policies_path = repo_root / ".orchestrator" / "config" / "policies.json"
    if not policies_path.is_file():
        pytest.skip("policies.json live ausente")
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    cc = policies.get("context_compaction")
    assert cc and cc.get("enabled") is True
    assert cc.get("save_learning_before_compact") is True
