#Requires -Version 5.1
# Migration 0.4.25 -> 0.4.26
# Onboarding vendor-neutro + varredura de bugs abertos.
#
# Aplicado automaticamente pelo update (sem mudanca de layout .orchestrator/):
# - Bloco `orchestrator:how-to-use` anexado a CLAUDE.md/AGENTS.md/GEMINI.md/KIMI.md
#   pelo Generate-Adapters (idempotente por marcador).
# - Repair-AgentHooks remove hooks que disparam 1 processo por chamada de
#   ferramenta (graphify hook-guard) — backup em .orchestrator/backups/.
# - mode=merge agora recebe deep-merge aditivo: chaves novas do template entram
#   em config/*.json preservando os valores do usuario (bug-003).
#
# Nota de encoding (bug-028): adapters gerados antes de 0.4.26 podem ter dupla
# codificacao (documentacao -> "documentaAAo"). O bloco novo e gravado correto;
# para conteudo antigo ja corrompido, regenere o arquivo ou corrija a mao.
param()
Write-Host '[OK] Migration 0.4.25-to-0.4.26 applied.'
