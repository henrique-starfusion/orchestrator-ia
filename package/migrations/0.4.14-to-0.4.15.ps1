#Requires -Version 5.1
# Migration 0.4.14 -> 0.4.15
# Codex Windows sandbox fix: elimina hang causado por CreateProcessAsUserW erro 740
# quando --sandbox workspace-write é usado sem elevação.
# - policies.json: agent_infra_fail_fast_count (default 3) — mata processo após N
#   ocorrências do marcador 740 no stream (CliExecutor fail-fast)
# - agents/profiles/codex.json: notes documenta override automático para
#   danger-full-access no Windows (os.name==nt); sandbox_flags mantém workspace-write
# - agents/process.py: INFRA_FAIL_MARKERS + infra_fail_fast_count + _reader fail-fast
# - agents/base_adapters.py: build_command override sandbox Windows
# - config.py: RuntimeLimits.agent_infra_fail_fast_count
# - diagnostics.py: features codex_infra_failfast + codex_sandbox_windows_override
param()
Write-Host '[OK] Migration 0.4.14-to-0.4.15 applied.'
