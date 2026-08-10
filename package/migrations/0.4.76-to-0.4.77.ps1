#Requires -Version 5.1
# Migration 0.4.76 -> 0.4.77
# Correcao somente no runtime: nada a editar no projeto consumidor e nenhuma
# chave de configuracao nova.
#
# bug-112 — deteccao de loop respeita clausulas negadas e protege review contra
# vocabulario descritivo de defeito. Planner deixa de aplicar gates
# workspace_changes/tests_pass herdados de loop de codigo a task nao-codigo.
# same_issue_repeat_limit e maximum_iterations permanecem inalterados.
param()
Write-Host '[OK] Migration 0.4.76-to-0.4.77 applied.'
