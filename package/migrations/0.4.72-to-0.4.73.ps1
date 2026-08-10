#Requires -Version 5.1
# Migration 0.4.72 -> 0.4.73
# - Heartbeat do LOOP, nao so do agente. O `agent_progress` (0.4.28) so existe
#   enquanto um CLI esta no ar. Nos vaos — escolha de agentes, consolidacao,
#   gravacao de memoria, gate de documentacao, a troca de uma etapa para a
#   seguinte — NADA era emitido, e `updated_at` so muda em transicao de estado.
#   Resultado: `task status` mostrava a mesma linha por minutos e nao havia como
#   distinguir fase legitima de processo morto. Custou tres investigacoes
#   manuais na frota (ler o log inteiro + conferir o PID a mao) para concluir
#   "nao travou" — printbee 8e4329205f01 e trustsafe e89063f15776 estavam ambas
#   trabalhando.
#
# NADA A EDITAR neste projeto. Sem chave de config nova.
#
# Mudancas visiveis:
# - Evento novo `loop_progress` em `task logs` / `orchestrator_events`, com
#   `phase`, `phase_elapsed_s`, `elapsed_s`, `iteration`, `pid` e
#   `agent_active`. Quem consome a lista de tipos de evento precisa tolerar o
#   valor novo.
# - `task status` (e `orchestrator_status`) ganham o bloco `live`:
#   sinal usado, idade do sinal, fase, se ha agente no ar e se o PID dono esta
#   vivo. `task status --text` imprime a linha `[VIVO] ...`.
# - Cadencia = a do perfil do chamador (20s bloqueante, 30s polling), com piso
#   de 10s.
#
# NAO muda a decisao do reaper: `loop_progress` e excluido do calculo de
# silencio de proposito. Ele nasce de uma thread do processo dono e continuaria
# batendo com o loop travado num lock — conta-lo como progresso trocaria a fila
# parada de 11h do bug-090 por uma eterna. Prova que o processo vive, nao que o
# trabalho anda.
param()
Write-Host '[OK] Migration 0.4.72-to-0.4.73 applied.'
