#Requires -Version 5.1
# Migration 0.4.78 -> 0.4.79
#
# A1 - policies.json: "agent_timeout_by_role" passa a aceitar DOIS EIXOS por papel:
#
#     "executor": { "run_timeout": 2400, "idle_timeout": 1200 }
#
#     run_timeout  = teto de relogio da tentativa, NUNCA renovado por sinal.
#                    E exatamente o inteiro que existia ate a 0.4.78.
#     idle_timeout = tempo maximo SEM progresso observavel, renovado pelo sinal
#                    que o runtime ja emite (byte lido, ou mudanca no workspace).
#
#     O merge do template e ADITIVO: papel que ja existe no policies.json do
#     consumidor NAO e sobrescrito. Ou seja, quem ficou no formato antigo
#     (inteiro puro) continua com idle_timeout NULO e cai no
#     "agent_no_output_timeout_s" global - comportamento identico ao da 0.4.78.
#     Para ligar o eixo ocioso por papel, troque o inteiro pelo objeto acima.
#
# A2 - o backoff do retry de lancamento (bug-111) ganhou jitter aleatorio:
#     a espera fica em [base, base*1.5) em vez de fixa em 3s/8s/15s. Nao ha
#     chave nova de configuracao. A guarda de orcamento da task compara contra a
#     espera JA com jitter.
#
# Nenhum daemon, thread de poll ou processo de background e criado.
param()
Write-Host '[OK] Migration 0.4.78-to-0.4.79 applied.'
