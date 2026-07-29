#Requires -Version 5.1
# Migration 0.4.40 -> 0.4.41
# - bug-057: ORCHESTRATOR_CHILD_AGENT passa a ser flag por VALOR (vazio/'0'
#   nao e filho) em runtime, guard, Invoke-RoutedAgent e nos textos dos
#   adapters/skills — var vazia herdada nao faz o agente principal recusar o
#   orquestrador. Adapters sao regenerados por este update.
# - bug-058: findPowerShell (bin/orchestrator.js) ganha fallback por caminho
#   absoluto System32/Sysnative quando o PATH do shell nao tem PowerShell.
param()
Write-Host '[OK] Migration 0.4.40-to-0.4.41 applied.'
