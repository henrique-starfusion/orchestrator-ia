#Requires -Version 5.1
# Migration 0.4.35 -> 0.4.36
# Segunda rodada GuardLine.BR — tudo em codigo do runtime, sem mudanca de
# configuracao por projeto:
# - bug-048: descoberta de testes tambem roda nos repos git filhos tocados
#   pelos changed_files (pasta-mae de repos aninhados tinha teste "<none>").
# - bug-049: prompts com mojibake UTF-8/CP1252 ("exigÃªncia") sao reparados
#   na ingestao (create_task) antes de persistir/analisar.
param()
Write-Host '[OK] Migration 0.4.35-to-0.4.36 applied.'
