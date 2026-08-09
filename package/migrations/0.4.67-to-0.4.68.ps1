#Requires -Version 5.1
# Migration 0.4.67 -> 0.4.68
# - Deteccao de enfraquecimento de teste: le o diff dos arquivos de teste da
#   iteracao e adiciona issues NAO-BLOQUEANTES (VAL-TInn) ao resultado da
#   validacao deterministica, mais um bloco no prompt do validador. Nao reprova
#   sozinho: quem transforma em blocking e o juiz, se confirmar.
# - `orchestrator_status` e `orchestrator_result` ganham `degradations`: registro
#   unico do que o runtime aceitou degradar. Os campos antigos
#   (independent_validation, agent_auth_required, plan_refined) CONTINUAM
#   saindo — cliente que ja os consome nao quebra.
# - Novo: `orchestrator skills list` e `orchestrator skills install <pacote>`.
#   Instala pacotes de skills CURADOS em .orchestrator/skills/<pacote>/.
#   `orchestrator skills` sem argumento mantem o comportamento antigo (listar o
#   registry do projeto).
#
# Instale pacote de skills POR PROJETO. O skill_selector recebe a lista inteira
# a cada task: dezenas de descricoes extras encarecem tambem as tasks de codigo.
# Sem chave de config e sem mudanca automatica em disco.
param()
Write-Host '[OK] Migration 0.4.67-to-0.4.68 applied.'
