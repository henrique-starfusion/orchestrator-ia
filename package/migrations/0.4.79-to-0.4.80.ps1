#Requires -Version 5.1
# Migration 0.4.79 -> 0.4.80
#
# bug-116 - changed_files_since passa a comparar conteudo dos paths que ja
# estavam sujos no baseline. Nova edicao com o mesmo codigo XY e restauracao
# que remove o path do porcelain deixam de parecer entrega vazia.
#
# O recorte de custo e deliberado: somente paths sujos no inicio recebem
# SHA-256. Paths limpos continuam detectados pela mudanca do porcelain; nenhuma
# arvore completa e hasheada. A mesma regra cobre repos git filhos imediatos.
param()
Write-Host '[OK] Migration 0.4.79-to-0.4.80 applied.'
