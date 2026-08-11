#Requires -Version 5.1
# Migration 0.4.80 -> 0.4.81
#
# bug-117 - sync do pacote decide --depth pelo estado real do repositorio.
# Clone completo faz fetch sem profundidade e preserva ancestralidade para o
# merge ff-only; clone ja shallow conserva depth 1, atualiza por FETCH_HEAD e
# mostra como restaurar a historia com git fetch --unshallow origin.
#
# get.ps1 mantem clone --depth 1 somente para cache novo e descartavel.
param()
Write-Host '[OK] Migration 0.4.80-to-0.4.81 applied.'
