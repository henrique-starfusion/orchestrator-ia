#Requires -Version 5.1
# Migration 0.4.66 -> 0.4.67
# - bug-101: o teto da fase SELECTING_AGENTS deixa de ser 180s fixo e passa a
#   ser `skill_selection_timeout_s + PLANNER_REFINE_CAP_S` (padrao 120 + 300 =
#   420s). Efeito pratico: o refino de plano agora consegue de fato usar os 300s
#   que a config sempre prometeu. Antes morria aos ~180s com ZERO byte quando o
#   modelo era `fable` — 50% de perda medida no printbee.
#   Se voce baixou `skill_selection_timeout_s`, a fase encolhe junto: e por
#   construcao, para os dois tetos nunca mais se contradizerem.
# - bug-102: `orchestrator_status` passa a trazer `plan_refined: false` e
#   `plan_warning` quando o refino do plano falhou. A task continua rodando com
#   o plano deterministico (comportamento inalterado) — o que muda e o resultado
#   deixar de esconder isso.
# - bug-100: `pytest` com exit 5 (nenhum teste coletado) vira
#   `skipped/no_tests_collected` em vez de `failed/introduced`. Projeto sem
#   suite Python para de ser reprovado por ausencia de testes que nunca teve.
# Sem chave de config e sem mudanca em disco.
param()
Write-Host '[OK] Migration 0.4.66-to-0.4.67 applied.'
