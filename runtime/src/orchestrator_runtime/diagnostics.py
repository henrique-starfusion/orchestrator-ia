"""Diagnósticos de runtime (fingerprint para detectar MCP stale)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

# Arquivos cujo conteúdo muda o comportamento observável do MCP.
_FINGERPRINT_FILES = (
    "planning/analyzer.py",
    "mcp/tools.py",
    "execution/locks.py",
    "validation/deterministic.py",
)

# Capabilities estáveis para o cliente IDE checar sem depender só de VERSION.
FEATURES: tuple[str, ...] = (
    "extract_requirements_semver",
    "audit_complex_analysis_acs",
    "analyze_warnings",
    "independent_validation_hard_reject",
    "runtime_code_fingerprint",
)


def runtime_package_root() -> Path:
    """Diretório `runtime/` do pacote (pai de `src/orchestrator_runtime`)."""
    return Path(__file__).resolve().parents[2]


def code_fingerprint() -> dict[str, Any]:
    """Hash curto do código crítico + features.

    Use para comparar CLI local vs processo MCP: mesma VERSION pode servir
    módulos já importados (stale) até o Cursor reiniciar o servidor MCP.
    """
    src_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for rel in _FINGERPRINT_FILES:
        path = src_root / rel
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "sha256_16": digest.hexdigest()[:16],
        "files": list(_FINGERPRINT_FILES),
        "features": list(FEATURES),
        "module_path": str(src_root),
        "package_root": str(runtime_package_root()),
    }
