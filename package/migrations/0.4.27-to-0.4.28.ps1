#Requires -Version 5.1
# Migration 0.4.27 -> 0.4.28
# - Plano incompleto: o runtime manda CONTINUAR ate fechar (max_plan_continuations,
#   default 5 em policies.json) em vez de validar trabalho pela metade.
# - Heartbeat do CLI vira evento agent_progress: EXECUTING deixa de parecer travado
#   para quem observa por MCP/DB.
# - orchestrator-guard: isencoes de caminho passaram a normalizar separador
#   (com barra normal, .wolf/ .claude/ .cursor/ nao eram isentos e o guard
#   bloqueava edicao nesses diretorios).
param()
Write-Host '[OK] Migration 0.4.27-to-0.4.28 applied.'
