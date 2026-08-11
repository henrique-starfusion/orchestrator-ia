#Requires -Version 5.1
# Migration 0.4.82 -> 0.4.83
#
# Issue #12 - regra de desenvolvimento "nunca supor".
#
# Nenhuma mutacao imperativa e necessaria. A entrada managed de
# package/manifest.json instala .orchestrator/rules/nunca-supor.md tanto em
# projeto novo quanto em projeto existente durante o update (RefreshManaged).
param()
Write-Host '[OK] Migration 0.4.82-to-0.4.83 applied.'
