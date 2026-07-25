#Requires -Version 5.1
# Migration 0.4.15 -> 0.4.16
# Fixes PrintBee: WriteLock asyncio single-flight, classificação docs word-boundary,
# transição idempotente same-state, TTL auto-cancel RECEIVED, prompt child sem subagentes.
# - policies.json: stale_received_ttl_hours (default 6) — auto-cancela RECEIVED zumbis
# - execution/locks.py: _owner_task tracking; segunda task asyncio -> TimeoutError imediato
# - planning/analyzer.py: \bdoc word-boundary + impl-vence-docs
# - tasks/state_machine.py: same-state -> no-op (não levanta InvalidTransitionError)
# - tasks/repository.py: transition() com same-state -> return sem evento
# - tasks/service.py: _cancel_stale_received() + bloco ORCHESTRATOR_CHILD_AGENT no prompt
# - diagnostics.py: 5 novas features de 0.4.16
param()
Write-Host '[OK] Migration 0.4.15-to-0.4.16 applied.'
