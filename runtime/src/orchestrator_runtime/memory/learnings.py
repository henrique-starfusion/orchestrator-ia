"""Learning extraction, digest, and durable persistence (0.4.14).

Learn-then-compact: BEFORE the chat/context is compacted, the runtime writes a
rich `learning` record so a later conversation can recover what a prior task
did, decided, and hit — instead of the weak truncated-prompt episode.

Pure helpers here (data in, files/strings out); `TaskService` orchestrates the
ordering (save learning → THEN compact artifacts) so a compaction can never run
without the learning already on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIGEST_MAX_CHARS_DEFAULT = 1500
TRUNCATE_ARTIFACT_CHARS_DEFAULT = 20000
_TRUNCATED_MARKER = "\n[TRUNCATED]"


def extract_learning(
    task: Any,
    *,
    success: bool,
    strategy: str | None = None,
    run_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the enriched learning payload from a terminal task + run context.

    run_ctx (optional) carries loop locals not persisted on the task:
    changed_files, test_results, last_validation.
    """
    ctx = run_ctx or {}
    analysis = task.analysis if isinstance(task.analysis, dict) else {}
    plan = task.plan if isinstance(task.plan, dict) else {}
    changed = list(dict.fromkeys(ctx.get("changed_files") or []))
    tests = ctx.get("test_results") or []
    validation = ctx.get("last_validation") or {}

    blockers: list[str] = []
    for issue in validation.get("blocking_issues") or []:
        if isinstance(issue, dict):
            blockers.append(f"{issue.get('id')}: {issue.get('description')}")
        else:
            blockers.append(str(issue))

    test_summary = [
        {"command": t.get("command"), "status": t.get("status")}
        for t in tests
        if isinstance(t, dict)
    ]

    decisions: list[str] = []
    roles = plan.get("roles") or {}
    if roles:
        decisions.append(
            "roles=" + ", ".join(f"{r}:{a}" for r, a in roles.items())
        )
    if strategy or plan.get("strategy"):
        decisions.append(f"strategy={strategy or plan.get('strategy')}")

    return {
        "task_id": task.id,
        "objective": task.prompt,
        "status": task.status.value,
        "success": bool(success),
        "score": task.last_score,
        "task_type": task.task_type,
        "strategy": strategy or plan.get("strategy"),
        "roles": roles,
        "decisions": decisions,
        "skills_used": list(analysis.get("selected_skills") or []),
        "files_touched": changed,
        "tests": test_summary,
        "blockers": blockers,
        "recommendations": _recommendations(task, success, blockers),
        "documentation": task.documentation_review or {},
    }


def _recommendations(task: Any, success: bool, blockers: list[str]) -> list[str]:
    recs: list[str] = []
    if success:
        recs.append("Tarefa concluída; reutilizar estratégia/skills registradas.")
    else:
        recs.append(
            f"Retomar do estado {task.status.value}; resolver blockers antes de reexecutar."
        )
    if blockers:
        recs.append("Blockers pendentes: " + "; ".join(blockers[:3]))
    return recs


def build_digest(
    learning: dict[str, Any], *, max_chars: int = DIGEST_MAX_CHARS_DEFAULT
) -> str:
    """Compact session digest (≤ max_chars) the IDE client keeps after terminal.

    Everything the next conversation needs without the verbose poll history.
    """
    lines: list[str] = [
        f"task_id: {learning['task_id']}",
        f"status: {learning['status']} "
        f"(success={learning['success']}, score={learning.get('score')})",
        f"objetivo: {str(learning['objective'])[:220]}",
    ]
    if learning.get("strategy"):
        lines.append(f"estratégia: {learning['strategy']}")
    if learning.get("skills_used"):
        lines.append("skills: " + ", ".join(learning["skills_used"]))
    files = learning.get("files_touched") or []
    if files:
        lines.append(
            "arquivos: "
            + ", ".join(files[:12])
            + (" …" if len(files) > 12 else "")
        )
    if learning.get("tests"):
        lines.append(
            "testes: "
            + "; ".join(
                f"{t.get('command')}={t.get('status')}"
                for t in learning["tests"][:6]
            )
        )
    if learning.get("blockers"):
        lines.append("blockers: " + " | ".join(learning["blockers"][:5]))
    for rec in (learning.get("recommendations") or [])[:3]:
        lines.append(f"next: {rec}")
    lines.append(f"learning_path: {learning_rel_path(learning['task_id'])}")
    digest = "\n".join(lines)
    if len(digest) > max_chars:
        digest = digest[: max_chars - len(_TRUNCATED_MARKER)] + _TRUNCATED_MARKER
    return digest


def learning_rel_path(task_id: str) -> str:
    return f".orchestrator/memory/learnings/{task_id}.md"


def render_markdown(learning: dict[str, Any], digest: str) -> str:
    def _bullets(items: list[Any]) -> str:
        return "\n".join(f"- {i}" for i in items) if items else "- (nenhum)"

    tests = learning.get("tests") or []
    test_lines = (
        "\n".join(
            f"- `{t.get('command')}` → {t.get('status')}" for t in tests
        )
        if tests
        else "- (nenhum)"
    )
    return (
        f"# Learning {learning['task_id']}\n\n"
        f"- status: {learning['status']}\n"
        f"- success: {learning['success']}\n"
        f"- score: {learning.get('score')}\n"
        f"- task_type: {learning.get('task_type')}\n"
        f"- strategy: {learning.get('strategy')}\n\n"
        f"## Objetivo\n\n{learning['objective']}\n\n"
        f"## Decisões\n\n{_bullets(learning.get('decisions') or [])}\n\n"
        f"## Skills usadas\n\n{_bullets(learning.get('skills_used') or [])}\n\n"
        f"## Arquivos tocados\n\n{_bullets(learning.get('files_touched') or [])}\n\n"
        f"## Testes\n\n{test_lines}\n\n"
        f"## Blockers\n\n{_bullets(learning.get('blockers') or [])}\n\n"
        f"## Recomendações\n\n{_bullets(learning.get('recommendations') or [])}\n\n"
        f"## Digest\n\n```\n{digest}\n```\n"
    )


def memory_content(learning: dict[str, Any]) -> str:
    """Keyword-rich searchable content for the `learning` memory row.

    search_memories() scores by token overlap, so pack objective + files +
    blockers + skills into the content — that is what a later task queries.
    """
    parts = [
        f"learning task={learning['task_id']}",
        f"status={learning['status']}",
        f"success={learning['success']}",
        f"type={learning.get('task_type')}",
        f"objetivo: {learning['objective']}",
    ]
    if learning.get("skills_used"):
        parts.append("skills: " + ", ".join(learning["skills_used"]))
    if learning.get("files_touched"):
        parts.append("arquivos: " + ", ".join(learning["files_touched"][:20]))
    if learning.get("blockers"):
        parts.append("blockers: " + " | ".join(learning["blockers"][:5]))
    if learning.get("recommendations"):
        parts.append("recomendações: " + " | ".join(learning["recommendations"]))
    return "\n".join(parts)


def write_markdown(mem_dir: Path, learning: dict[str, Any], digest: str) -> Path:
    mem_dir.mkdir(parents=True, exist_ok=True)
    path = mem_dir / f"{learning['task_id']}.md"
    path.write_text(render_markdown(learning, digest), encoding="utf-8")
    return path


def update_index(memory_root: Path, learning: dict[str, Any], digest: str) -> None:
    """Append/replace this task's entry in memory/index.json (most-recent first)."""
    index_path = memory_root / "index.json"
    entries: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = loaded
            elif isinstance(loaded, dict) and isinstance(loaded.get("learnings"), list):
                entries = loaded["learnings"]
        except (json.JSONDecodeError, OSError):
            entries = []
    entries = [e for e in entries if e.get("task_id") != learning["task_id"]]
    entries.insert(
        0,
        {
            "task_id": learning["task_id"],
            "status": learning["status"],
            "success": learning["success"],
            "score": learning.get("score"),
            "objective": str(learning["objective"])[:200],
            "path": learning_rel_path(learning["task_id"]),
            "digest": digest,
        },
    )
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps({"learnings": entries[:200]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_WOLF_START = "<!-- ORCH:LAST-TASK -->"
_WOLF_END = "<!-- /ORCH:LAST-TASK -->"


def update_wolf_status(wolf_dir: Path, learning: dict[str, Any]) -> None:
    """Update .wolf/STATUS.md with a managed 'Last orchestrator task' block.

    No-op when .wolf/ is absent. Idempotent: replaces the managed block if it
    already exists, otherwise inserts it right after the H1 title.
    """
    status_path = wolf_dir / "STATUS.md"
    if not status_path.is_file():
        return
    block = (
        f"{_WOLF_START}\n"
        f"## Last orchestrator task\n\n"
        f"- task: `{learning['task_id']}` → **{learning['status']}** "
        f"(success={learning['success']}, score={learning.get('score')})\n"
        f"- objetivo: {str(learning['objective'])[:160]}\n"
        f"- arquivos: {', '.join((learning.get('files_touched') or [])[:8]) or '(nenhum)'}\n"
        f"- learning: {learning_rel_path(learning['task_id'])}\n"
        f"{_WOLF_END}"
    )
    text = status_path.read_text(encoding="utf-8")
    if _WOLF_START in text and _WOLF_END in text:
        pre = text.split(_WOLF_START, 1)[0]
        post = text.split(_WOLF_END, 1)[1]
        new_text = pre + block + post
    else:
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("# "):
                insert_at = i + 1
                break
        lines.insert(insert_at, "\n" + block + "\n")
        new_text = "\n".join(lines)
    status_path.write_text(new_text, encoding="utf-8")


def append_cerebrum_pitfall(wolf_dir: Path, learning: dict[str, Any]) -> None:
    """Append a Do-Not-Repeat pitfall to .wolf/cerebrum.md when a task fails.

    Only for failed tasks with blockers; deduplicates by task_id.
    """
    if learning.get("success") or not learning.get("blockers"):
        return
    cerebrum_path = wolf_dir / "cerebrum.md"
    if not cerebrum_path.is_file():
        return
    text = cerebrum_path.read_text(encoding="utf-8")
    if learning["task_id"] in text:
        return
    entry = (
        f"- [orchestrator {learning['task_id']}] "
        f"{learning['status']} em '{str(learning['objective'])[:80]}'. "
        f"Blockers: {'; '.join(learning['blockers'][:2])}. "
        f"Ver {learning_rel_path(learning['task_id'])}.\n"
    )
    if "## Do-Not-Repeat" in text:
        head, _, tail = text.partition("## Do-Not-Repeat")
        # insert right after the header line
        rest = tail.split("\n", 1)
        header_line = rest[0]
        body = rest[1] if len(rest) > 1 else ""
        new_text = head + "## Do-Not-Repeat" + header_line + "\n" + entry + body
    else:
        new_text = text.rstrip() + "\n\n## Do-Not-Repeat\n\n" + entry
    cerebrum_path.write_text(new_text, encoding="utf-8")


def compact_result_artifacts(
    results_dir: Path, *, max_chars: int = TRUNCATE_ARTIFACT_CHARS_DEFAULT
) -> list[str]:
    """Truncate large *.txt agent-output artifacts in results/{task_id}/.

    Runs AFTER the learning is saved. Returns the list of compacted files.
    """
    if not results_dir.is_dir():
        return []
    compacted: list[str] = []
    for path in results_dir.glob("*.txt"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(text) <= max_chars:
            continue
        head = max_chars - len(_TRUNCATED_MARKER)
        path.write_text(text[:head] + _TRUNCATED_MARKER, encoding="utf-8")
        compacted.append(path.name)
    return compacted
