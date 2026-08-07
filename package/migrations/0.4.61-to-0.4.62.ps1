#Requires -Version 5.1
# Migration 0.4.61 -> 0.4.62
# - bug-088: redacao de segredos passa a apagar o VALOR, nao a linha inteira.
#   Efeito colateral bom: saida de agente que so MENCIONA secret/token/password
#   deixa de ser destruida antes do parse do runtime. Sem chave de config.
# - bug-089: orchestrator_status ganha "independent_validation" e, quando
#   falso, "validation_warning". Nao muda gate nem score — so reporta.
# Nada a migrar em disco.
param()
Write-Host '[OK] Migration 0.4.61-to-0.4.62 applied.'
