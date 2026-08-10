#Requires -Version 5.1
# Migration 0.4.70 -> 0.4.71
# - bug-108 (CRITICO): `orchestrator run --prompt "..."` estava QUEBRADO desde a
#   0.4.66 em todos os projetos — `Usage: run [OPTIONS] {service} {json_out}` /
#   `No such option: --prompt`. O helper `_drain_queue` engoliu o
#   `@app.command("run")` e o comando real ficou orfao. Corrigido.
#   APOS ESTE UPDATE: recarregue o servidor MCP (ou reinicie o cliente). Um MCP
#   longo-lived mantem o modulo antigo em memoria e continua recusando o `run`.
#   Confira com `orchestrator version --json` (compare `sha256_16` do CLI com o
#   do MCP: diferentes = MCP stale).
# - bug-107: o outcome `premise_mismatch` (executor declara que a premissa da
#   tarefa esta incorreta) FABRICAVA sucesso perfeito: `last_score = 1.0` e
#   episodio com `success=True`, sem validator nenhum, com
#   `require_independent_validation` ligado. Pior, era honrado DEPOIS de uma
#   rejeicao gravada, apagando o veredito (printbee efeaee6fd306: COMPLETED
#   score=1.0 com `rejected score=0.1` em disco).
#
# NADA A EDITAR neste projeto. Sem chave de config nova.
#
# Mudancas visiveis:
# - task fechada por `premise_mismatch` agora vem com `last_score` NULO. Cliente
#   que assume numero em task COMPLETED precisa tratar nulo.
# - `analysis.premise_verified` (false) acompanha `analysis.premise_mismatch`.
# - alegacao de premissa DEPOIS de uma validacao rejeitada nao fecha mais como
#   sucesso: vira INCOMPLETE com motivo `premise_mismatch_after_rejection`.
# - degradacao nova `premise_declared_unverified` no `status`/`result`: diz que
#   nada foi entregue e que ninguem julgou a alegacao.
#
# Historico: tasks fechadas por este caminho ANTES da 0.4.71 continuam no banco
# com score 1.0, e `strategy_performance` mantem os numeros inflados. A tabela e
# write-only (nenhum modulo a le), entao nao ha decisao a recalcular; se quiser
# a metrica limpa, zere a tabela no .orchestrator/data/orchestrator.db.
param()
Write-Host '[OK] Migration 0.4.70-to-0.4.71 applied.'
