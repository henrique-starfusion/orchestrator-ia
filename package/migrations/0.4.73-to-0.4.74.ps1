#Requires -Version 5.1
# Migration 0.4.73 -> 0.4.74
# - MAIS DE UMA TASK POR PROJETO. Ate a 0.4.73 o projeto era serializado por
#   inteiro: uma task ativa, as outras em QUEUED, e a segunda esperava a primeira
#   terminar (25 a 40 min). O que precisa ser exclusivo nao e o projeto, e o
#   CODIGO — duas tasks em pastas diferentes nunca se atrapalham.
#
# CHAVE NOVA: `max_parallel_tasks` (default 3 no template).
#   1 restaura exatamente o comportamento da 0.4.73.
#
# Como a garantia funciona (o trabalho todo acontece na branch local, sem
# worktree): e ADMISSAO mais DETECCAO, nao impossibilidade por construcao.
#
#   ADMISSAO  duas tasks so rodam juntas se os escopos de arquivo forem
#             comprovadamente disjuntos. Escopo VAZIO significa DESCONHECIDO e
#             sobrepoe tudo — task sem escopo declarado serializa, como antes.
#             O teto tambem vale: escopo separa codigo, o teto protege a maquina
#             (foi exaustao de recurso que produziu o 0xC0000142 do bug-109).
#
#   DETECCAO  agente que escreve fora do escopo nao e impedido na hora; o desvio
#             sobe como degradacao `scope_violation` no status/result. A
#             disciplina de higiene git injetada no prompt do agente (bug-077:
#             seis quase-arrastoes num dia no printbee) deixa de ser precaucao e
#             passa a ser condicao de funcionamento.
#
# De onde sai o escopo:
#   1. `orchestrator run --scope src/api --scope tests/api` (o dono manda);
#   2. senao, os caminhos que o PROPRIO PEDIDO nomeia e que existem no projeto.
#      Pedido sem caminho nenhum devolve escopo vazio, e vazio serializa. E burro
#      de proposito: escopo inventado AUTORIZARIA o par que nao podia rodar junto.
#
# Mudancas visiveis:
# - `orchestrator run` aceita `--scope` (repetivel).
# - degradacao nova `scope_violation` no status/result.
# - `TESTING` continua exclusivo (lock proprio): duas suites no mesmo diretorio
#   disputam build dir, cache e porta, e a falha resultante nao existe no codigo
#   de nenhuma das duas.
# - o loop NAO segura mais o write lock do workspace. Quem usava a existencia
#   desse arquivo de lock como "alguem esta trabalhando" precisa parar: o sinal
#   de vida agora e o evento `loop_progress`, com pid POR TASK.
# - SQLite passa a WAL + busy_timeout=15s (tres escritores por projeto).
#
# NADA A EDITAR neste projeto: a chave nova entra pelo merge do template. Para
# voltar ao comportamento da 0.4.73, ponha `max_parallel_tasks: 1` no
# `.orchestrator/config/policies.json`.
param()
Write-Host '[OK] Migration 0.4.73-to-0.4.74 applied.'
