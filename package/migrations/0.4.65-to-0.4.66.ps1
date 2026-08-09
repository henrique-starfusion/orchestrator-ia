#Requires -Version 5.1
# Migration 0.4.65 -> 0.4.66
# - bug-098: o CLI passa a ESPERAR as tasks que ele tirou da fila antes de sair.
#   Mudanca de comportamento visivel: `orchestrator run` agora pode demorar mais
#   do que a propria task, porque executa tambem a proxima da fila que ele
#   destravou. Antes essa task era transicionada para RECEIVED e abandonada (11
#   min no printbee em 09/08; 47 HORAS em 07/08). O servidor MCP nao muda.
# - bug-099: `Update-Agents.ps1` nao substitui mais o binario de um CLI em
#   execucao — reporta `deferred_running`. Rodar `orchestrator update` de dentro
#   do Claude Code passa a ADIAR o update do proprio `claude`; rode fora da
#   sessao para atualiza-lo. Isso e proposital: substituir .exe em uso no
#   Windows nao pula o update, ele QUEBRA o CLI (EBUSY + instalacao parcial).
# Sem chave de config e sem mudanca em disco.
param()
Write-Host '[OK] Migration 0.4.65-to-0.4.66 applied.'
