"""Resultados tipados de teste."""

from typing import TypedDict


class TestResultDict(TypedDict, total=False):
    command: str
    category: str
    exit_code: int | None
    duration_s: float
    stdout: str
    stderr: str
    status: str
    discovery_source: str
    failure_kind: str | None
