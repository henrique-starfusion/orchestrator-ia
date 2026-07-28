#Requires -Version 5.1
# Migration 0.4.34 -> 0.4.35
# Correcoes da auditoria GuardLine.BR — tudo em codigo do runtime, sem mudanca
# de configuracao por projeto:
# - bug-045: detect_loop com fronteira de palavra; clausula condicional e hit
#   isolado em prompt longo nao impoem mais loop (criterios de template errado).
# - bug-046: secao "Criterios: a; b; c" do prompt vira ACs declarados e vence
#   o template do loop.
# - bug-047: changed_files_since enxerga repos git aninhados (pasta-mae com
#   repos filhos, layout GuardLine.BR) — workspace_changes volta a funcionar.
param()
Write-Host '[OK] Migration 0.4.34-to-0.4.35 applied.'
