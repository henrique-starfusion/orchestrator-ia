#Requires -Version 5.1
# Migration 0.4.29 -> 0.4.30
# - bug-041: prompt grande passa a ir por stdin. Antes, argv estourava o teto de
#   32767 chars do Windows (WinError 206, "Linha de comando muito longa") e o
#   agente NUNCA nascia: 30 bytes de saida, zero arquivo tocado, e a task ainda
#   seguia para validacao terminando INCOMPLETE com score 0.8.
#   Passou a estourar na 0.4.27, quando o prompt do executor comecou a carregar
#   skills + rules + loop alem do pedido do usuario.
# Os profiles de codex e claude ganham nota sobre invoke.prompt_via; nao ha
# mudanca de comportamento a migrar em disco.
param()
Write-Host '[OK] Migration 0.4.29-to-0.4.30 applied.'
