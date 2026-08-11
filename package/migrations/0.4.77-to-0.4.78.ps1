#Requires -Version 5.1
# Migration 0.4.77 -> 0.4.78
#
# bug-113 - policies.json ganha:
#     "orphan_queued_adopt_after_s": 120
# O merge do template adiciona a chave aos consumidores. 0 desliga a adocao.
# Nenhum daemon ou poll periodico e instalado; status/list/watch/create_task
# reutilizam a thread de execucao e o lock curto queue.adopt.lock.
param()
Write-Host '[OK] Migration 0.4.77-to-0.4.78 applied.'
