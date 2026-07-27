#Requires -Version 5.1
# Migration 0.4.28 -> 0.4.29
# - O runtime passa a saber QUEM o chamou (claude-code / cursor / codex / mcp /
#   cli) e ajusta o tratamento: eco no console so onde ha console, cadencia de
#   heartbeat mais curta em sessao bloqueante, e o CLI que ja esta ocupado
#   atendendo o usuario deixa de ser a primeira escolha para executor.
# - bug-040: o evento agent_progress da 0.4.28 ia so para o EventBus (stderr +
#   memoria) e NUNCA era persistido. Quem observa por MCP/DB — o publico que a
#   correcao existia para atender — seguia vendo EXECUTING mudo. Agora grava em
#   task_events.
# Nada a migrar em disco: mudanca e de runtime.
param()
Write-Host '[OK] Migration 0.4.28-to-0.4.29 applied.'
