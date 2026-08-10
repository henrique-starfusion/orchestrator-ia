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
    # 0.4.14 — learn-then-compact context
    "memory/learnings.py",
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
    # 0.4.14 — aprendizado durável antes da compactação de contexto do chat
    "learn_then_compact_context",
    # 0.4.15 — fail-fast no stream (740) + override sandbox Windows
    "codex_infra_failfast",
    "codex_sandbox_windows_override",
    # 0.4.16 — fixes PrintBee: lock reentrante asyncio, classificação docs, transição idempotente, TTL RECEIVED, prompt child
    "writelock_asyncio_singleflight",
    "produção_not_docs",
    "same_state_transition_noop",
    "stale_received_ttl_autocancel",
    "child_agent_no_subagents_prompt",
    # 0.4.18 — restrição anti-subagente sempre no prompt + fail-fast collab Wait
    "child_agent_restriction_always_on",
    "codex_collab_wait_failfast",
    # 0.4.19 — fila FIFO por workspace (QUEUED + dequeue automático)
    "workspace_task_queue",
    # 0.4.21 — executor/corrector modelo forte; validator intermediário
    "role_model_executor_strong",
    # 0.4.23 — import rules/skills/adapters existentes antes do install
    "preinstall_import_existing_config",
    # 0.4.24 — cancel hard-stop, MCP stale gate, registry prune, fila TASK_QUEUED
    "cancel_terminal_hard_stop",
    "mcp_stale_run_reject",
    "registry_prune_test_fixtures",
    "task_queued_event",
    # 0.4.25 — planner Claude: melhor modelo + fallback se cota esgotar
    "planner_model_quota_fallback",
    # 0.4.60 — agente pendurado não come o orçamento; órfã RECEIVED é adotada;
    # timeout rotulado pela evidência
    "agent_no_output_watchdog",
    "orphan_received_adoption",
    "timeout_issue_by_evidence",
    # 0.4.61 — fan-out: subtarefa em worktree próprio, fusão por patch
    "parallel_subtask_worktrees",
    "subtask_patch_merge",
    # 0.4.62 — redação por valor (não apaga a linha) e aviso de validação
    # sem veredito independente
    "value_scoped_secret_redaction",
    "independent_validation_flag",
    # 0.4.63 — deadlock de pipe no stdin, reaper de task não-terminal e
    # auto-reparo de CLI de agente quebrado
    "stdin_written_after_readers",
    "stale_execution_reaper",
    "agent_broken_cli_detection",
    "agent_auto_repair",
    # 0.4.64 — falta de credencial de agente sobe para o chat (só o dono resolve)
    "agent_auth_blocker_surfaced",
    # 0.4.66 — a fila entrega a task E espera quem vai executa-la; update nunca
    # substitui binario de CLI em execucao
    "queue_handoff_joined",
    "agent_update_defers_running_cli",
    # 0.4.67 — o teto da fase comporta o refino; plano cru e declarado; pytest
    # sem teste coletado deixa de ser cobrado como regressao
    "selecting_cap_fits_planner_refine",
    "plan_refined_flag",
    "pytest_no_tests_not_a_failure",
    # 0.4.68 — integridade de teste no diff, validador que observa em vez de
    # confiar, registro único de degradação e pacotes de skills curados
    "test_weakening_detection",
    "validator_claims_are_falsifiable",
    "degradation_ledger",
    "curated_skill_packs",
    # 0.4.69 — task nascida com o workspace ocupado entra na fila, não fica
    # esperando em RECEIVED fora dela
    "create_enqueues_when_busy",
    # 0.4.70 — o teto da task cabe executar→julgar→corrigir→julgar; quem executa
    # não leva o orçamento do veredito; sem orçamento a validação degrada em vez
    # de estourar
    "task_budget_fits_correction_round",
    "verdict_time_reserved",
    "validation_skipped_not_failed",
    "reaper_names_the_clock",
    "provider_outage_not_reinstall",
    # 0.4.71 — o outcome declarado pelo executor deixa de fabricar score
    # perfeito, e não apaga mais uma rejeição já gravada
    "premise_score_not_fabricated",
    "premise_never_overrides_rejection",
    # 0.4.72 — processo que não nasceu não é CLI quebrado
    "launch_failure_not_reinstall",
    # 0.4.73 — o loop dá sinal de vida também onde nenhum agente roda, e o
    # `status` diz se andou sem exigir leitura do log inteiro
    "loop_heartbeat_between_agents",
    "status_answers_is_it_alive",
    # 0.4.74 — mais de uma task por projeto, admitida por escopo de arquivo
    "parallel_tasks_per_project",
    "file_scope_admission",
    "scope_violation_reported",
    "per_task_run_context",
    "sqlite_wal_multi_writer",
    # 0.4.75 — um jeito padrão de acompanhar, para ninguém inventar laço de shell
    "task_watch_streams_events",
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
