"""Repositório de tarefas e eventos."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from orchestrator_runtime.events import EventType, RuntimeEvent
from orchestrator_runtime.memory.database import (
    AgentPerformanceRow,
    AgentRunRow,
    ArtifactRow,
    DocumentationUpdateRow,
    MemoryRow,
    RoutingDecisionRow,
    StrategyPerformanceRow,
    TaskEventRow,
    TaskIterationRow,
    TaskRow,
    TestRunRow,
    ValidationIssueRow,
    ValidationRoundRow,
    create_session_factory,
    dumps,
    loads,
)
from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    TaskConstraints,
    TaskRecord,
)
from orchestrator_runtime.tasks.state_machine import TaskState, assert_transition


class TaskRepository:
    def __init__(self, db_path: str) -> None:
        self._Session = create_session_factory(db_path)

    def session(self) -> Session:
        return self._Session()

    def _to_row(self, task: TaskRecord) -> TaskRow:
        return TaskRow(
            id=task.id,
            prompt=task.prompt,
            project_path=task.project_path,
            task_type=task.task_type,
            languages_json=dumps(task.languages),
            risk=task.risk,
            complexity=task.complexity,
            requirements_json=dumps(task.requirements),
            acceptance_criteria_json=dumps(
                [c.model_dump() for c in task.acceptance_criteria]
            ),
            constraints_json=dumps(task.constraints.model_dump()),
            status=task.status.value,
            plan_json=dumps(task.plan) if task.plan is not None else None,
            analysis_json=dumps(task.analysis) if task.analysis is not None else None,
            documentation_review_json=(
                dumps(task.documentation_review)
                if task.documentation_review is not None
                else None
            ),
            iteration=task.iteration,
            last_score=task.last_score,
            cancel_requested=1 if task.cancel_requested else 0,
            error=task.error,
        )

    def _from_row(self, row: TaskRow) -> TaskRecord:
        criteria_raw = loads(row.acceptance_criteria_json, [])
        return TaskRecord(
            id=row.id,
            prompt=row.prompt,
            project_path=row.project_path,
            task_type=row.task_type or "implementation",
            languages=loads(row.languages_json, []),
            risk=row.risk or "medium",
            complexity=row.complexity or "medium",
            requirements=loads(row.requirements_json, []),
            acceptance_criteria=[
                AcceptanceCriterion.model_validate(c) for c in criteria_raw
            ],
            constraints=TaskConstraints.model_validate(
                loads(row.constraints_json, {})
            ),
            status=TaskState(row.status),
            plan=loads(row.plan_json),
            analysis=loads(row.analysis_json),
            documentation_review=loads(row.documentation_review_json),
            iteration=row.iteration or 0,
            last_score=row.last_score,
            cancel_requested=bool(row.cancel_requested),
            error=row.error,
            created_at=(
                row.created_at.isoformat()
                if row.created_at
                else datetime.now(timezone.utc).isoformat()
            ),
            updated_at=(
                row.updated_at.isoformat()
                if row.updated_at
                else datetime.now(timezone.utc).isoformat()
            ),
        )

    def create(self, task: TaskRecord) -> TaskRecord:
        with self.session() as s:
            s.add(self._to_row(task))
            s.commit()
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self.session() as s:
            row = s.get(TaskRow, task_id)
            return self._from_row(row) if row else None

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        with self.session() as s:
            rows = s.scalars(
                select(TaskRow).order_by(TaskRow.created_at.desc()).limit(limit)
            ).all()
            return [self._from_row(r) for r in rows]

    def save(self, task: TaskRecord) -> TaskRecord:
        task.updated_at = datetime.now(timezone.utc).isoformat()
        with self.session() as s:
            row = s.get(TaskRow, task.id)
            if row is None:
                s.add(self._to_row(task))
            else:
                row.prompt = task.prompt
                row.project_path = task.project_path
                row.task_type = task.task_type
                row.languages_json = dumps(task.languages)
                row.risk = task.risk
                row.complexity = task.complexity
                row.requirements_json = dumps(task.requirements)
                row.acceptance_criteria_json = dumps(
                    [c.model_dump() for c in task.acceptance_criteria]
                )
                row.constraints_json = dumps(task.constraints.model_dump())
                row.status = task.status.value
                row.plan_json = dumps(task.plan) if task.plan is not None else None
                row.analysis_json = (
                    dumps(task.analysis) if task.analysis is not None else None
                )
                row.documentation_review_json = (
                    dumps(task.documentation_review)
                    if task.documentation_review is not None
                    else None
                )
                row.iteration = task.iteration
                row.last_score = task.last_score
                row.cancel_requested = 1 if task.cancel_requested else 0
                row.error = task.error
                row.updated_at = datetime.now(timezone.utc)
            s.commit()
        return task

    def transition(
        self,
        task: TaskRecord,
        new_state: TaskState,
        *,
        reason: str,
        agent: str | None = None,
        evidence: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> TaskRecord:
        assert_transition(task.status, new_state)
        previous = task.status
        task.status = new_state
        if error:
            task.error = error
        self.save(task)
        self.add_event(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.STATE_CHANGED,
                agent=agent,
                data={
                    "from": previous.value,
                    "to": new_state.value,
                    "reason": reason,
                    "evidence": evidence or {},
                    "error": error,
                    "summary": f"{previous.value} -> {new_state.value}",
                },
            )
        )
        return task

    def add_event(self, event: RuntimeEvent) -> None:
        with self.session() as s:
            s.add(
                TaskEventRow(
                    task_id=event.task_id,
                    timestamp=event.timestamp,
                    type=event.type.value,
                    role=event.role,
                    agent=event.agent,
                    data_json=dumps(event.data),
                )
            )
            s.commit()

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = s.scalars(
                select(TaskEventRow)
                .where(TaskEventRow.task_id == task_id)
                .order_by(TaskEventRow.id.asc())
            ).all()
            return [
                {
                    "timestamp": r.timestamp,
                    "type": r.type,
                    "role": r.role,
                    "agent": r.agent,
                    "data": loads(r.data_json, {}),
                }
                for r in rows
            ]

    def add_agent_run(self, **kwargs: Any) -> None:
        with self.session() as s:
            s.add(AgentRunRow(**kwargs))
            s.commit()

    def add_test_run(self, **kwargs: Any) -> None:
        with self.session() as s:
            s.add(TestRunRow(**kwargs))
            s.commit()

    def add_validation_round(self, **kwargs: Any) -> None:
        with self.session() as s:
            s.add(ValidationRoundRow(**kwargs))
            s.commit()

    def add_validation_issue(self, **kwargs: Any) -> None:
        with self.session() as s:
            s.add(ValidationIssueRow(**kwargs))
            s.commit()

    def add_routing_decision(self, task_id: str, strategy: str, decision: dict) -> None:
        with self.session() as s:
            s.add(
                RoutingDecisionRow(
                    task_id=task_id,
                    strategy=strategy,
                    decision_json=dumps(decision),
                )
            )
            s.commit()

    def add_iteration(self, task_id: str, iteration: int, score: float | None, status: str, notes: dict) -> None:
        with self.session() as s:
            s.add(
                TaskIterationRow(
                    task_id=task_id,
                    iteration=iteration,
                    score=score,
                    status=status,
                    notes_json=dumps(notes),
                )
            )
            s.commit()

    def add_artifact(self, task_id: str, kind: str, path: str, meta: dict | None = None) -> None:
        with self.session() as s:
            s.add(
                ArtifactRow(
                    task_id=task_id,
                    kind=kind,
                    path=path,
                    meta_json=dumps(meta or {}),
                )
            )
            s.commit()

    def list_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = s.scalars(
                select(ArtifactRow).where(ArtifactRow.task_id == task_id)
            ).all()
            return [
                {"kind": r.kind, "path": r.path, "meta": loads(r.meta_json, {})}
                for r in rows
            ]

    def save_documentation_update(self, task_id: str, payload: dict[str, Any]) -> None:
        with self.session() as s:
            s.add(
                DocumentationUpdateRow(
                    task_id=task_id,
                    required=1 if payload.get("required", True) else 0,
                    reason=payload.get("reason", ""),
                    files_updated_json=dumps(payload.get("files_updated", [])),
                    files_reviewed_json=dumps(payload.get("files_reviewed", [])),
                    validation=payload.get("validation", "pending"),
                    payload_json=dumps(payload),
                )
            )
            s.commit()

    def save_memory(self, kind: str, content: str, task_id: str | None = None, meta: dict | None = None) -> None:
        with self.session() as s:
            s.add(
                MemoryRow(
                    task_id=task_id,
                    kind=kind,
                    content=content,
                    meta_json=dumps(meta or {}),
                )
            )
            s.commit()

    def search_memories(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = query.lower()
        with self.session() as s:
            rows = s.scalars(
                select(MemoryRow).order_by(MemoryRow.id.desc()).limit(100)
            ).all()
            scored = []
            for r in rows:
                text = (r.content or "").lower()
                score = sum(1 for token in q.split() if token and token in text)
                if score:
                    scored.append((score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "content": r.content,
                    "meta": loads(r.meta_json, {}),
                    "task_id": r.task_id,
                }
                for _, r in scored[:limit]
            ]

    def update_agent_performance(self, agent: str, success: bool, duration_s: float, score: float | None = None) -> None:
        with self.session() as s:
            row = s.scalars(
                select(AgentPerformanceRow).where(AgentPerformanceRow.agent == agent)
            ).first()
            if row is None:
                row = AgentPerformanceRow(agent=agent, runs=0, successes=0, failures=0, avg_duration_s=0.0)
                s.add(row)
            row.runs = (row.runs or 0) + 1
            if success:
                row.successes = (row.successes or 0) + 1
            else:
                row.failures = (row.failures or 0) + 1
            prev = row.avg_duration_s or 0.0
            row.avg_duration_s = prev + (duration_s - prev) / row.runs
            if score is not None:
                row.last_score = score
            s.commit()

    def update_strategy_performance(self, strategy: str, success: bool, score: float | None = None) -> None:
        with self.session() as s:
            row = s.scalars(
                select(StrategyPerformanceRow).where(
                    StrategyPerformanceRow.strategy == strategy
                )
            ).first()
            if row is None:
                row = StrategyPerformanceRow(
                    strategy=strategy, runs=0, successes=0, failures=0, avg_score=0.0
                )
                s.add(row)
            row.runs = (row.runs or 0) + 1
            if success:
                row.successes = (row.successes or 0) + 1
            else:
                row.failures = (row.failures or 0) + 1
            if score is not None:
                prev = row.avg_score or 0.0
                row.avg_score = prev + (score - prev) / row.runs
            s.commit()
