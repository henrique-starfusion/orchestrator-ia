#Requires -Version 5.1
# Migration 0.4.74 -> 0.4.75
# - `orchestrator task watch <id>`: UM jeito padrao de acompanhar uma task.
#
# Motivo concreto: no trustsafe apareceram TRES tarefas de segundo plano vigiando
# a MESMA task (c210252e2c58), cada uma com um `until ... sleep` escrito a mao e
# com intervalo diferente (120s, 150s, 150s). Nao era task duplicada — era o
# VIGIA duplicado. O `| grep -qE` engolia a saida, o painel ficava mudo entre os
# `sleep`, e a sessao recriava o vigia achando que a task tinha travado.
#
# O material ja existia desde a 0.4.73 (cada batida do heartbeat e um evento com
# fase, idade da fase, agent_active e pid). Faltava transmitir, e faltava a regra
# dizendo que era assim que se fazia — sem isso cada sessao inventava a sua.
#
# NADA A EDITAR neste projeto. Sem chave de config nova.
#
# Mudancas visiveis:
# - comando novo `orchestrator task watch <id>`, com `--verbose` (inclui cada
#   batida), `--all` (reproduz o historico), `--json` (JSONL: uma linha por
#   evento) e `--timeout N` (desiste de olhar; NAO cancela a task). Sai com
#   codigo != 0 se a task nao terminar COMPLETED — mesmo contrato do `run`.
# - as regras dos SEIS adaptadores (claude, codex, gemini, kimi, opencode,
#   cursor) passam a mandar usar `task watch` e a PROIBIR laco de shell. Este
#   merge sobrescreve os arquivos gerenciados do adaptador; regra escrita por
#   voce em arquivo proprio nao e tocada.
param()
Write-Host '[OK] Migration 0.4.74-to-0.4.75 applied.'
