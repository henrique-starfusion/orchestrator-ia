"""Artifact path helpers."""

from pathlib import Path


def results_dir(orchestrator_root: Path, task_id: str) -> Path:
    path = orchestrator_root / "runtime" / "results" / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path
