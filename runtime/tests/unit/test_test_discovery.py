from orchestrator_runtime.testing.discovery import TestDiscovery


def test_test_discovery_python(project):
    (project / "tests").mkdir()
    (project / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    found = TestDiscovery().discover(project)
    assert any(t.category == "unit" for t in found)
    assert any("pytest" in " ".join(t.command) for t in found)
