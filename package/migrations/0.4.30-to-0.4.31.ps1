#Requires -Version 5.1
# Migration 0.4.30 -> 0.4.31
# - bug-042: Update-Agents decidia sucesso pelo exit code. O kimi instalado por
#   instalador nativo no Windows imprime "auto-update is not supported" e sai
#   com exit 0 — entao entrava no relatorio como "updated" sem ter atualizado.
#   Agora quem decide e a saida do CLI, nao o exit code.
# - Estrategia native-installer: esse mesmo agente passa a ser atualizado pelo
#   instalador oficial (URL em Get-AgentNativeInstallerMap, curada no codigo e
#   nunca lida da saida do CLI). Baixado para .orchestrator/runtime/installers/
#   com SHA256 no log. -NoNativeInstaller desliga.
# Nada a migrar em disco: mudanca e nos scripts do pacote.
param()
Write-Host '[OK] Migration 0.4.30-to-0.4.31 applied.'
