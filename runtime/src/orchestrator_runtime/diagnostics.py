"""Diagnósticos de runtime (fingerprint para detectar MCP stale)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

# Arquivos cujo conteúdo muda o comportamento observável do MCP.
_FINGERPRINT_FILES = (
    "diagnostics.py",
    "planning/analyzer.py",
    "mcp/tools.py",
    "execution/locks.py",
    "validation/deterministic.py",
    # 0.4.11 — o grosso do comportamento do workflow vive aqui
    "tasks/service.py",
    "tasks/state_machine.py",
    "testing/discovery.py",
    "agents/process.py",
)

# Capabilities estáveis para o cliente IDE checar sem depender só de VERSION.
FEATURES: tuple[str, ...] = (
    "extract_requirements_semver",
    "audit_complex_analysis_acs",
    "analyze_warnings",
    "independent_validation_hard_reject",
    "runtime_code_fingerprint",
    # 0.4.10 — auditoria PrintBee
    "git_baseline_timeout",
    "agent_empty_output_guard",
    "validator_infra_not_merit",
    "delegate_finalizes_task",
    # 0.4.11 — transcrições PrintBee 2026-07-24
    "requires_input_structured",
    "impl_intent_overrides_analysis",
    "stack_aware_test_harness",
    "cancel_kills_children",
    "blocked_by_lock_visible",
    "timeout_no_output_rotation",
    "planner_refine_cap",
    # 0.4.12 — OpenWolf/Graphify/Superpowers/Caveman always-on nos prompts
    "always_on_agent_tooling",
    # 0.4.13 — skill selection com modelo leve antes dos complexos
    "skill_selection_fast_model",
)


def runtime_package_root() -> Path:
    """Diretório `runtime/` do pacote (pai de `src/orchestrator_runtime`)."""
    return Path(__file__).resolve().parents[2]


def _hash_fingerprint_files() -> str:
    src_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for rel in _FINGERPRINT_FILES:
        path = src_root / rel
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


# Snapshot do código efetivamente carregado neste processo Python.
# Health/CLI devem reportar ESTE valor — não o hash “ao vivo” do disco —
# senão um MCP longo-lived parece fresco após edits no disco sem reload.
_LOADED_SHA256_16 = _hash_fingerprint_files()


def code_fingerprint() -> dict[str, Any]:
    """Fingerprint do código carregado neste processo + check vs disco.

    `sha256_16` = módulos já importados (comportamento real do MCP/CLI).
    Compare CLI vs MCP: se diferirem, o processo MCP está stale.
    Se `modules_stale` for True neste processo, o disco avançou sem reload.
    """
    src_root = Path(__file__).resolve().parent
    disk_sha = _hash_fingerprint_files()
    return {
        "sha256_16": _LOADED_SHA256_16,
        "disk_sha256_16": disk_sha,
        "modules_stale": disk_sha != _LOADED_SHA256_16,
        "files": list(_FINGERPRINT_FILES),
        "features": list(FEATURES),
        "module_path": str(src_root),
        "package_root": str(runtime_package_root()),
    }
