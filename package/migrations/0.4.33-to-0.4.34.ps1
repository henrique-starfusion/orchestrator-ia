#Requires -Version 5.1
# Migration 0.4.33 -> 0.4.34
# - orchestrator-guard avisava UMA vez por sessao e calava. Medido numa sessao de
#   12h no proprio repo do orquestrador: disparou as 01:03 e nunca mais, com
#   dezenas de arquivos de codigo editados direto depois. Agora rearma a cada
#   ORCHESTRATOR_GUARD_REARM_MIN minutos (padrao 20) e informa quantos arquivos
#   ja foram editados direto na sessao.
# - O marcador virou JSON ({edits,last_at}). Marcadores antigos (texto puro) sao
#   lidos como "primeiro aviso" — sem migracao necessaria.
param()
Write-Host '[OK] Migration 0.4.33-to-0.4.34 applied.'
