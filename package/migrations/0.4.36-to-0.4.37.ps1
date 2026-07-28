#Requires -Version 5.1
# Migration 0.4.36 -> 0.4.37
# Terceira rodada GuardLine.BR — tudo em codigo do runtime, sem mudanca de
# configuracao por projeto:
# - bug-050: ferramenta de teste ausente no PATH (go/make/cargo/...) nao conta
#   mais como teste falho. Pre-flight which() no TestRunner.run_all reporta
#   skipped + failure_kind tool_missing; o portao tests_passed nao bloqueia
#   por ambiente (task 3b56b92278e9: validador aprovou 1.0 e a task terminou
#   INCOMPLETE por make inexistente na maquina).
param()
Write-Host '[OK] Migration 0.4.36-to-0.4.37 applied.'
