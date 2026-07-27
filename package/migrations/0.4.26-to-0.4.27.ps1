#Requires -Version 5.1
# Migration 0.4.26 -> 0.4.27
# Loops de execucao + regras do projeto no prompt do executor.
#
# Sem mudanca de layout .orchestrator/. O que passa a valer automaticamente:
# - O pedido escolhe um loop (bug|mvp|landing|conteudo|saas) por palavra-chave;
#   override explicito com prefixo "/loop-<id>" no prompt ou --loop no CLI.
#   Sem match, nenhum loop e imposto (comportamento anterior preservado).
# - As regras do projeto (.cursor/rules/*.mdc e .orchestrator/rules/**) sao
#   descobertas por frontmatter e as mais relevantes entram no prompt do
#   executor. Regras com alwaysApply:true entram sempre.
#
# Para tirar proveito: garanta que suas regras tenham `description` no
# frontmatter — e ela que alimenta a selecao por relevancia.
param()
Write-Host '[OK] Migration 0.4.26-to-0.4.27 applied.'
