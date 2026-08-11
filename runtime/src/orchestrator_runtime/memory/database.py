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
    event,
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


class AgentProcessRow(Base):
    """CLI de agente LANCADO — identidade recuperavel apos a morte do runtime.

    bug-119 — `agent_runs` so nasce quando o processo TERMINA e nunca teve
    coluna de PID; o unico rastreador de processo vivo era um set em memoria
    (`CliExecutor._active_pids`), que morre junto com o runtime. Sem esta linha
    nao ha como saber, de outro processo, que aquele CLI existe.

    `image` + `create_time` sao a identidade lida do S.O. no lancamento: sem os
    dois conferindo, o PID nao autoriza kill nenhum (Windows recicla numero).
    `owner_pid` e o processo do runtime que lancou — dono morto e uma das duas
    evidencias de orfandade (a outra e a task ter chegado a estado terminal).
    """

    __tablename__ = "agent_processes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), index=True, nullable=False)
    project_path = Column(Text, nullable=False)
    role = Column(String(64), nullable=True)
    agent = Column(String(64), nullable=True)
    pid = Column(Integer, nullable=False)
    image = Column(Text, nullable=True)
    create_time = Column(Float, nullable=True)
    owner_pid = Column(Integer, nullable=False)
    started_at = Column(String(64), nullable=True)
    finished_at = Column(String(64), nullable=True)
    reaped_at = Column(String(64), nullable=True)


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


# 0.4.74 — quanto um escritor espera antes de desistir com "database is locked".
# Uma transação deste runtime é um INSERT ou um UPDATE de uma linha; 15s é ordem
# de magnitude acima do pior caso e ainda muito abaixo de qualquer timeout de
# papel, então esperar é sempre melhor que falhar.
SQLITE_BUSY_TIMEOUT_MS = 15_000


def create_session_factory(db_path: str) -> sessionmaker[Session]:
    """Engine SQLite preparada para VÁRIOS escritores.

    0.4.74 — o default do SQLite (`journal_mode=delete`) dá um lock de arquivo
    inteiro por escrita: qualquer segundo escritor leva `database is locked` na
    hora. Até a 0.4.73 isso não aparecia porque só havia uma task ativa por
    projeto — a serialização escondia o problema. Com tasks concorrentes há três
    escritores por projeto no mesmo processo, mais uma thread de heartbeat por
    task (0.4.73), mais os outros processos (MCP, CLI, reaper).

    WAL deixa leitor e escritor conviverem; `busy_timeout` faz o escritor
    ESPERAR sua vez em vez de estourar. `synchronous=NORMAL` é o par usual de WAL
    (durável contra crash de processo, que é o caso real aqui; só perde no crash
    de sistema operacional, onde a task já morreu de qualquer forma).
    """
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"timeout": SQLITE_BUSY_TIMEOUT_MS / 1000},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    return json.loads(text)
