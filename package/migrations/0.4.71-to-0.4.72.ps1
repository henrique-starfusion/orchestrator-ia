#Requires -Version 5.1
# Migration 0.4.71 -> 0.4.72
# - bug-109: processo que NAO NASCEU era tratado como CLI quebrado. No trustsafe
#   (task 22a07ed7e2de) dois correctors sairam exit=3221225794 (0xC0000142,
#   STATUS_DLL_INIT_FAILED) em 0s com zero byte nos dois streams. Sem saida, o
#   classificador caiu na regra do fast-fail mudo, devolveu `install`, e o
#   auto-reparo tentou reinstalar os dois — a PROPRIA reinstalacao falhou com o
#   mesmo exit code. Quatro lancamentos de processo falharam em ~1s: o sinal era
#   da maquina, nao do CLI.
#
# NADA A EDITAR neste projeto. Sem chave de config nova.
#
# Mudancas visiveis:
# - `failure_kind` do evento `agent_repair` ganha um QUARTO valor: `launch`
#   (junto de install/auth/service), agora acompanhado de `exit_code`. Quem
#   consome esse campo precisa tratar o valor novo.
# - degradacao nova `agent_launch_failed` no `status`/`result`, com acao de
#   MAQUINA (liberar memoria/processos), nao de CLI.
# - agente que falha por falta de recurso NAO e mais reinstalado.
#
# Escopo estreito de proposito: access violation (0xC0000005) e stack overrun
# (0xC0000409) ficam FORA — aqueles sao crash de binario, onde reinstalar pode
# de fato resolver.
param()
Write-Host '[OK] Migration 0.4.71-to-0.4.72 applied.'
