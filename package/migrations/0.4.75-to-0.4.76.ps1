#Requires -Version 5.1
# Migration 0.4.75 -> 0.4.76
# Dois defeitos de runtime medidos em producao na 0.4.75. Correcao so no
# runtime: NADA A EDITAR neste projeto, sem chave de config nova.
#
# bug-110 — resume de task ORFA matava a task
#   printbee, task e9803cf77a43, 10/08 19:50:
#     status=FAILED  error='Transicao invalida: VALIDATING -> RETRIEVING_MEMORY'
#   O processo dono morreu com a task em VALIDATING. `can_resume` aceita
#   qualquer estado nao-terminal, entao o resume entrava — mas o loop so
#   transicionava para ANALYZING vindo de RECEIVED/WAITING_FOR_USER. Pulava a
#   re-entrada, seguia o fluxo e batia numa aresta que nao existe. Texto que
#   parece merito e era infra.
#   Agora: retomar de QUALQUER estado de meio de pipeline reinicia o pipeline
#   pelo ANALYZING, com o motivo 'restart after orphan (<estado>)' no historico.
#   Estado terminal continua imutavel — de la nao sai nada.
#
# bug-111 — falha de LANCAMENTO queimava iteracao e matava a task
#   trustsafe, 5 tasks INCOMPLETE em 10/08 (86b3abcb5cfa, 517010995d91,
#   22a07ed7e2de, c0e98dde9f27, e89063f15776):
#     error='AGENT-FAILED-NO-OUTPUT: corrector/codex exit=3221225794 sem mudancas'
#   3221225794 = 0xC0000142 STATUS_DLL_INIT_FAILED: o processo NAO NASCEU
#   (~132 processos node vivos na maquina). Desde a 0.4.72 isso ja era
#   classificado como `launch`, mas o servico so emitia o evento e devolvia a
#   mesma falha: ela caia no guard failed_no_output, QUEIMAVA uma iteracao e
#   disparava fallback para outro agente — que tambem nao nascia, porque a
#   falta de recurso era da MAQUINA. same_issue_repeat_limit estourava e a task
#   morria sem NENHUM julgamento de merito.
#   Agora: espera e reexecuta o MESMO agente com backoff (3s, 8s, 15s),
#   respeitando o orcamento restante da task, SEM reinstalar nada (a
#   reinstalacao ja foi medida falhando com o mesmo exit code). Cada tentativa
#   emite AGENT_REPAIR e aparece em `task logs`. Esgotadas as tentativas, o
#   resultado continua sendo infra, nunca merito.
param()
Write-Host '[OK] Migration 0.4.75-to-0.4.76 applied.'
