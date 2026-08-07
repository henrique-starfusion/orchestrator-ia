#Requires -Version 5.1
# Migration 0.4.60 -> 0.4.61
# - Fan-out: subtarefas paralelas com worktree proprio e fusao por patch.
#   policies.json ganha "max_parallel_subtasks": 4.
#   O gate continua sendo "allow_parallel_workspace_writes" (false por padrao,
#   ja existente): NADA muda de comportamento em quem nao ligar a chave.
# - Requisitos para o fan-out: repo git com pelo menos um commit. Sem HEAD o
#   runtime segue sequencial (nao falha).
# - Diretorios novos, criados sob demanda e limpos ao fim da task:
#     .orchestrator/runtime/worktrees/<task-id>/<subtask-id>
#     .orchestrator/runtime/patches/<task-id>/<subtask-id>.patch
#   Worktree orfao de versao anterior nao existe; nada a limpar aqui.
param()
Write-Host '[OK] Migration 0.4.60-to-0.4.61 applied.'
