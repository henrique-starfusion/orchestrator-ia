#Requires -Version 5.1
# Migration 0.4.68 -> 0.4.69
# - bug-103: `create_task` passa a ENFILEIRAR (QUEUED) quando o workspace ja
#   esta ocupado, em vez de deixar a task em RECEIVED. RECEIVED fica FORA de
#   `list_queued`, entao a cadeia de dequeue nem a enxergava — sobrava a adocao
#   de orfa, uma por vez e so com poll. Medido no printbee: 2h45min e 2h47min de
#   espera para tasks que nunca comecaram.
#
# Mudanca visivel: task criada por `orchestrator_run` (MCP) ou `task create` com
# outra em execucao agora nasce em QUEUED, com `queued_behind:<id>|pos=N` no
# campo `error` e `queue_position` no status. Antes nascia RECEIVED sem posicao.
# Cliente que tratava "RECEIVED" como "vai comecar ja" deve olhar QUEUED tambem.
#
# `run_task` continua promovendo QUEUED -> RECEIVED quando o workspace libera:
# o caminho de execucao nao muda.
# Sem chave de config e sem mudanca em disco.
param()
Write-Host '[OK] Migration 0.4.68-to-0.4.69 applied.'
