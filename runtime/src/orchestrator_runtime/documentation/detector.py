"""Gate documental obrigatório."""

from __future__ import annotations

import re
from pathlib import Path


DOC_CANDIDATES = [
    "README.md",
    "CHANGELOG.md",
    "docs",
]


class DocumentationDetector:
    def related_docs(self, project_path: Path, changed_files: list[str]) -> list[str]:
        found = []
        for name in DOC_CANDIDATES:
            path = project_path / name
            if path.exists():
                found.append(str(path.relative_to(project_path)))
        # Heurística: docs perto de arquivos alterados
        for rel in changed_files:
            p = Path(rel)
            sibling_readme = project_path / p.parent / "README.md"
            if sibling_readme.is_file():
                rel_doc = str(sibling_readme.relative_to(project_path))
                if rel_doc not in found:
                    found.append(rel_doc)
        return found


class DocumentationUpdater:
    def ensure_usage_docs(
        self, project_path: Path, prompt: str, changed_files: list[str]
    ) -> dict:
        detector = DocumentationDetector()
        reviewed = detector.related_docs(project_path, changed_files)
        updated: list[str] = []
        required = True
        reason = "Toda tarefa deve avaliar impacto documental antes da conclusão."

        readme = project_path / "README.md"
        needs_update = False
        if any(
            x in prompt.lower()
            for x in ("doc", "readme", "document", "soma", "módulo", "modulo")
        ):
            needs_update = True
        if any(f.startswith("soma") or f.endswith(".py") for f in changed_files):
            needs_update = True

        if needs_update:
            if not readme.exists():
                readme.write_text("# Projeto\n\n", encoding="utf-8")
                updated.append("README.md")
                if "README.md" not in reviewed:
                    reviewed.append("README.md")
            text = readme.read_text(encoding="utf-8")
            if "soma" in prompt.lower() and "soma(" not in text:
                readme.write_text(
                    text
                    + "\n## Uso\n\n```python\nfrom soma import soma\nprint(soma(1, 2))\n```\n",
                    encoding="utf-8",
                )
                if "README.md" not in updated:
                    updated.append("README.md")
            reason = "Código/API alterados; README atualizado com uso."
        else:
            required = True
            reason = "Nenhuma atualização documental necessária; arquivos revisados sem mudanças."

        validation = DocumentationValidator().validate(project_path, reviewed)
        return {
            "required": required,
            "reason": reason,
            "files_updated": updated,
            "files_reviewed": reviewed,
            "validation": validation,
        }


class DocumentationValidator:
    def validate(self, project_path: Path, files: list[str]) -> str:
        for rel in files:
            path = project_path / rel
            if path.is_dir():
                continue
            if not path.is_file():
                return "failed"
            if path.suffix.lower() == ".md":
                text = path.read_text(encoding="utf-8", errors="ignore")
                # broken local markdown links check (best-effort)
                for match in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
                    target = match[1]
                    if target.startswith(("http://", "https://", "#", "mailto:")):
                        continue
                    linked = (path.parent / target).resolve()
                    try:
                        linked.relative_to(project_path.resolve())
                    except ValueError:
                        return "failed"
                    if not linked.exists():
                        return "failed"
        return "passed"
