#Requires -Version 5.1
# Migration 0.4.41 -> 0.4.42
# - bug-059 (fila presa atras de task CANCELLED): _run_git sem deadlock
#   (arquivo em vez de PIPE, fsmonitor off, kill de arvore no timeout);
#   _busy_task_id ignora task terminal zumbi em _running_tasks; cancel-check
#   antes do pre-loop; cancel() desfila a proxima. Tudo codigo do runtime —
#   nada por projeto. Se um processo MCP antigo estiver com coroutine
#   congelada, recarregar o Cursor/MCP uma vez apos este update.
param()
Write-Host '[OK] Migration 0.4.41-to-0.4.42 applied.'
