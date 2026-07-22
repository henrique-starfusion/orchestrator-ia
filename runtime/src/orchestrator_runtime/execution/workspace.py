"""Workspace helpers."""

from pathlib import Path


def list_project_files(project_path: Path, limit: int = 200) -> list[str]:
    files = []
    for p in project_path.rglob("*"):
        if p.is_file():
            try:
                files.append(str(p.relative_to(project_path)))
            except ValueError:
                continue
            if len(files) >= limit:
                break
    return files
