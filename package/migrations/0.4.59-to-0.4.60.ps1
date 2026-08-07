#Requires -Version 5.1
# Migration 0.4.59 -> 0.4.60
# - bug-086: watchdog de silencio. policies.json ganha
#     "agent_no_output_timeout_s": 900
#   Mata o agente que passa a janela sem NENHUMA saida E sem tocar no
#   workspace. 0 desliga. Sem a chave, o default do runtime (900s) vale.
# - bug-085: adocao de task RECEIVED orfa. policies.json ganha
#     "orphan_received_adopt_after_s": 120
#   Qualquer processo vivo do orquestrador adota a orfa (inclusive no poll de
#   status/list). 0 desliga.
# - bug-087: rotulo de timeout por evidencia (AGENT-NO-OUTPUT-HANG /
#   TASK-BUDGET-EXHAUSTED / AGENT-TIMEOUT-NO-CHANGES / AGENT-TIMEOUT-NO-OUTPUT).
#   Só codigo; nada a migrar.
# As duas chaves entram pelo merge do template no update; nada manual.
param()
Write-Host '[OK] Migration 0.4.59-to-0.4.60 applied.'
