#Requires -Version 5.1
# Migration 0.4.64 -> 0.4.65
# - bug-096: o reaper de task nao-terminal passa a medir silencio pelo SINAL DE
#   VIDA mais recente (transicao de estado OU evento/heartbeat), nao so por
#   `updated_at`. Sem chave de config e sem mudanca em disco.
#
# IMPORTANTE PARA QUEM OPERA: na 0.4.63/0.4.64, apagar um
# .orchestrator/runtime/locks/workspace.write.lock a mao com task rodando podia
# cancelar execucao SAUDAVEL (o reaper enxergava "sem dono vivo" e `updated_at`
# fica congelado durante trabalho de agente). A partir da 0.4.65 o heartbeat
# recente segura o reaper sozinho. Ainda assim: so apague lock depois de
# confirmar que o PID gravado nele nao existe mais.
param()
Write-Host '[OK] Migration 0.4.64-to-0.4.65 applied.'
