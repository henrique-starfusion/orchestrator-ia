#Requires -Version 5.1
# Migration 0.4.9 -> 0.4.10
# Runtime fixes (código, sem mudança de layout .orchestrator/):
# - git status com timeout (anti-hang RECEIVED no Windows)
# - AGENT-EMPTY-OUTPUT: stdout vazio do executor não vira rejeição falsa de workspace_changes
# - Validator: falha de infra (sandbox Windows 740) não conta como rejeição de mérito; fallback validator
# - delegate finaliza a task (fim dos órfãos RECEIVED no DB)
# Limpeza opcional de órfãos antigos (delegates RECEIVED pré-0.4.10):
#   python -c "import sqlite3; c=sqlite3.connect('.orchestrator/data/orchestrator.db'); c.execute(\"update tasks set status='CANCELLED' where status='RECEIVED' and prompt like '[delegate:%'\"); c.commit()"
param()
Write-Host '[OK] Migration 0.4.9-to-0.4.10 applied.'
