#Requires -Version 5.1
# Migration 0.4.69 -> 0.4.70
# - bug-104: o teto da task nao cabia o percurso que o runtime pretende fazer.
#   Uma volta com correcao soma planner 900 + executor 2400 + tester 600 +
#   validator 1200 + corrector 2400 + validator 1200 = 8700s, contra um
#   `maximum_duration_seconds` de 3600. Toda task que usava o orcamento dos
#   papeis morria no meio, sempre ANTES do validator (o ultimo a ser chamado).
#   Medido no printbee: b259e8f0c168 terminou FAILED com "Orcamento de tempo
#   insuficiente para validator (timeout_s=0)".
#
# NADA A EDITAR neste projeto: o piso e aplicado ao CARREGAR a configuracao, e
# vale mesmo com 3600 escrito no policies.json. O valor pedido fica registrado
# em `duration_floor_raised_from`.
#
# Mudancas visiveis:
# - `maximum_duration_seconds` efetivo sobe para pelo menos 8700 (ou a soma dos
#   seus proprios `agent_timeout_by_role`, se voce os customizou). Teto e limite
#   de paciencia: subir NAO faz task nenhuma demorar mais, so para de matar as
#   que ainda estavam trabalhando.
# - `executor` e `corrector` passam a devolver 600s do restante para o veredito,
#   entao o timeout de invocacao deles pode vir menor que em 0.4.69.
# - Task sem orcamento para validar NAO falha mais: sai com o veredito
#   deterministico e uma degradacao `validation_not_independent` cujo `action`
#   manda aumentar o `maximum_duration_seconds`.
#
# O template passa a trazer 8700; projetos existentes mantem o proprio arquivo.
#
# - bug-105: a mensagem do reaper de task nao-terminal escrevia "{estado} ha Ns"
#   usando a IDADE DA TASK, nao o tempo na fase. Agora diz "em {estado}, criada
#   ha Ns e sem sinal de vida ha Ms". Quem tiver alerta/grep casando com o texto
#   antigo precisa ajustar o padrao.
#   A mesma mensagem passa a anexar "a ultima validacao ja havia APROVADO
#   (score=X)" quando o reaper pega uma task que ja tinha veredito aprovado
#   gravado — trustsafe 529cc0476c4e foi cancelada exatamente assim.
# - bug-106: falha do SERVICO do provedor virava `install` e disparava
#   reinstalacao inutil do CLI (ate 300s por ocorrencia). Nova categoria
#   `service`: registra, NAO reinstala, e sobe como degradacao
#   `agent_service_down`. Quem consome `failure_kind` do evento `agent_repair`
#   passa a ver um terceiro valor alem de `install` e `auth`.
#   O prior do `opencode` no roteador cai de 0.6 para 0.3 (medicao de frota:
#   0/3 apos reinstalacao bem-sucedida). Ele continua disponivel quando
#   escolhido explicitamente com --validator/--executor.
param()
Write-Host '[OK] Migration 0.4.69-to-0.4.70 applied.'
