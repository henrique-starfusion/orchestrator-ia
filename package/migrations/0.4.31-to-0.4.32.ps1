#Requires -Version 5.1
# Migration 0.4.31 -> 0.4.32
# - Probe-Agents volta a rodar por PADRAO em install/update (opt-out:
#   -SkipAgentProbes). Estava desligado por default e o probe-results.json da
#   frota estava parado em skipped=true desde 19/07.
# - O probe passou a CONFERIR o profile contra o CLI instalado: pede o help do
#   comando que o profile realmente invoca (`codex exec --help`, nao o de topo)
#   e verifica se cada flag existe. Antes so checava se `--help` saia 0.
# - profile do kimi corrigido: prompt_flag "-p" (era null -> prompt ia como
#   argumento nu e o CLI respondia "unknown command"). kimi era fallback em 80
#   planos da frota.
param()
Write-Host '[OK] Migration 0.4.31-to-0.4.32 applied.'
