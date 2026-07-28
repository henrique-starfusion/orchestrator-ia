#Requires -Version 5.1
# Migration 0.4.38 -> 0.4.39
# - bug-055: Repair-GraphifyHooks.ps1 entra no fluxo de install/update/propagate.
#   Hooks git do graphify (post-commit/post-checkout) ganham pythonw.exe no
#   interpretador pinado + CREATE_NO_WINDOW no Popen destacado — sem janela de
#   console piscando a cada commit. Reaplicado a cada update porque
#   `graphify hook install` sobrescreve .git/hooks (nao versionado).
#   O proprio update desta versao ja aplica o reparo; nada manual aqui.
param()
Write-Host '[OK] Migration 0.4.38-to-0.4.39 applied.'
