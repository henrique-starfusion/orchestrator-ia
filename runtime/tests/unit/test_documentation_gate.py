from orchestrator_runtime.documentation import DocumentationUpdater


def test_documentation_gate(project):
    review = DocumentationUpdater().ensure_usage_docs(
        project,
        "Crie modulo soma com documentacao",
        ["soma/core.py"],
    )
    assert review["validation"] == "passed"
    assert "README.md" in review["files_reviewed"] or review["files_updated"]
