"""Fingerprint de código para detectar MCP stale."""

from __future__ import annotations

from typer.testing import CliRunner

from orchestrator_runtime.cli import app
from orchestrator_runtime.diagnostics import FEATURES, code_fingerprint


def test_code_fingerprint_stable_shape():
    fp = code_fingerprint()
    assert len(fp["sha256_16"]) == 16
    assert "runtime_code_fingerprint" in fp["features"]
    assert set(FEATURES).issubset(set(fp["features"]))
    assert fp["module_path"]
    assert "disk_sha256_16" in fp
    assert "modules_stale" in fp
    # Neste processo de teste, disco == módulos carregados
    assert fp["modules_stale"] is False
    assert fp["disk_sha256_16"] == fp["sha256_16"]
    assert code_fingerprint()["sha256_16"] == fp["sha256_16"]


def test_cli_version_json():
    runner = CliRunner()
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0, result.output
    assert "code_fingerprint" in result.output
    assert "0.4.7" in result.output or "version" in result.output
