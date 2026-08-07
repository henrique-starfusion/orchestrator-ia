#Requires -Version 5.1
# Migration 0.4.63 -> 0.4.64
# - bug-095: falta de credencial de agente passa a subir para o chat.
#   `orchestrator_status`/`task status` ganham `agent_auth_required` e
#   `action_required`; `orchestrator_result` popula `remaining_issues` (que era
#   sempre []) e prefixa `message`; `run`/`task run` imprimem linha [ACAO].
#   Nenhuma chave de config e nenhuma mudanca em disco — so leitura dos eventos
#   `agent_repair` que a 0.4.63 ja gravava.
#
# Atencao para quem consome o MCP: `remaining_issues` deixou de ser sempre vazio.
# Cliente que assumia lista vazia agora recebe os pedidos de login pendentes.
param()
Write-Host '[OK] Migration 0.4.63-to-0.4.64 applied.'
