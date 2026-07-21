"""Persistência SQLite via SQLAlchemy."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

metadata = MetaData()


class Base(DeclarativeBase):
    metadata = metadata


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskRow(Base):
    __tablename__ = "tasks"

    id = Column(String(32), primary_key=True)
    prompt = Column(Text, nullable=False)
    project_path = Column(Text, nullable=False)
    task_type = Column(String(64), default="implementation")
    languages_json = Column(Text, default="[]")
    risk = Column(String(32), default="medium")
    complexity = Column(String(32), default="medium")
    requirements_json = Column(Text, default="[]")
    acceptance_criteria_json = Column(Text, default="[]")
    constraints_json = Column(Text, default="{}")
    status = Column(String(64), nullable=False)
    plan_json = Column(Text, nullable=True)
    analysis_json = Column(Text, nullable=True)
    documentation_review_json = Column(Text, nullable=True)
    iteration = Column(Integer, default=0)
    last_score = Column(Float, nullable=True)
    cancel_requested = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TaskEventRow(Base):
    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    timestamp = Column(String(64), nullable=False)
    type = Column(String(64), nullable=False)
    role = Column(String(64), nullable=True)
    agent = Column(String(64), nullable=True)
    data_json = Column(Text, default="{}")


class TaskIterationRow(Base):
    __tablename__ = "task_iterations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    iteration = Column(Integer, nullable=False)
    score = Column(Float, nullable=True)
    status = Column(String(64), nullable=True)
    notes_json = Column(Text, default="{}")


class SubtaskRow(Base):
    __tablename__ = "subtasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    role = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(64), default="pending")
    payload_json = Column(Text, default="{}")


class AgentRunRow(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    role = Column(String(64), nullable=False)
    agent = Column(String(64), nullable=False)
    model = Column(String(128), nullable=True)
    command_json = Column(Text, default="[]")
    cwd = Column(Text, nullable=True)
    started_at = Column(String(64), nullable=True)
    finished_at = Column(String(64), nullable=True)
    exit_code = Column(Integer, nullable=True)
    timed_out = Column(Integer, default=0)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    status = Column(String(64), default="unknown")
    changed_files_json = Column(Text, default="[]")


class RoutingDecisionRow(Base):
    __tablename__ = "routing_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    strategy = Column(String(128), nullable=True)
    decision_json = Column(Text, default="{}")


class TestRunRow(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    command = Column(Text, nullable=False)
    category = Column(String(64), nullable=False)
    exit_code = Column(Integer, nullable=True)
    duration_s = Column(Float, nullable=True)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    status = Column(String(64), default="unknown")
    discovery_source = Column(String(128), nullable=True)
    failure_kind = Column(String(64), nullable=True)


class ValidationRoundRow(Base):
    __tablename__ = "validation_rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    iteration = Column(Integer, default=0)
    status = Column(String(64), nullable=False)
    score = Column(Float, nullable=True)
    payload_json = Column(Text, default="{}")


class ValidationIssueRow(Base):
    __tablename__ = "validation_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    issue_id = Column(String(32), nullable=False)
    severity = Column(String(32), nullable=False)
    description = Column(Text, nullable=False)
    resolved = Column(Integer, default=0)


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    kind = Column(String(64), nullable=False)
    path = Column(Text, nullable=False)
    meta_json = Column(Text, default="{}")


class MemoryRow(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=True)
    kind = Column(String(64), nullable=False)
    content = Column(Text, nullable=False)
    meta_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class AgentPerformanceRow(Base):
    __tablename__ = "agent_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent = Column(String(64), unique=True, nullable=False)
    runs = Column(Integer, default=0)
    successes = Column(Integer, default=0)
    failures = Column(Integer, default=0)
    avg_duration_s = Column(Float, default=0.0)
    last_score = Column(Float, nullable=True)


class StrategyPerformanceRow(Base):
    __tablename__ = "strategy_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy = Column(String(128), unique=True, nullable=False)
    runs = Column(Integer, default=0)
    successes = Column(Integer, default=0)
    failures = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)


class DocumentationUpdateRow(Base):
    __tablename__ = "documentation_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    required = Column(Integer, default=1)
    reason = Column(Text, default="")
    files_updated_json = Column(Text, default="[]")
    files_reviewed_json = Column(Text, default="[]")
    validation = Column(String(64), default="pending")
    payload_json = Column(Text, default="{}")


def create_session_factory(db_path: str) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    return json.loads(text)
