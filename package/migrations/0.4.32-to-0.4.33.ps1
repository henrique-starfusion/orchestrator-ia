#Requires -Version 5.1
# Migration 0.4.32 -> 0.4.33
# - O branch `update` do instalador nunca chamava Probe-Agents: so o `install`
#   chamava. Resultado: o probe-results.json dos projetos propagados ficava
#   congelado na data da INSTALACAO. Medido na frota em 27/07: 9 projetos com
#   probe de 21/07, seis dias e varias versoes atras.
# - Agora todo update reconfere os agentes (opt-out: -SkipAgentProbes).
param()
Write-Host '[OK] Migration 0.4.32-to-0.4.33 applied.'
