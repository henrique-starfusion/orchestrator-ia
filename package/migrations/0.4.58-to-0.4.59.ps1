#Requires -Version 5.1
# Migration 0.4.58 -> 0.4.59
# - bug-083: o subagente orquestrador vira o AGENTE PADRAO da sessao.
#   claude code : .claude/settings.json  -> "agent": "orquestrador"
#   opencode    : opencode.json          -> "default_agent": "orquestrador"
#   (subagente opencode passa a mode: all — default_agent exige primary)
#   Aplicado pelo proprio update via Configure-AgentMcp.ps1; nada manual.
#   Valor de "agent" definido pelo usuario e preservado com aviso.
# - Sem equivalente em gemini/codex/kimi: nesses o desvio segue via
#   subagente + AGENTS.md.
param()
Write-Host '[OK] Migration 0.4.58-to-0.4.59 applied.'
