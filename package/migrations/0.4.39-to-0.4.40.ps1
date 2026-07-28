#Requires -Version 5.1
# Migration 0.4.39 -> 0.4.40
# Auditoria de uso da frota — tudo em codigo do runtime:
# - bug-056: stack em subdiretorios comuns (src/backend, src/frontend) sem
#   marcador na raiz nao fica mais sem teste. Quando raiz + extra_dirs nao
#   acham nada, o TestRunner varre subdiretorios ate profundidade 2 (pulando
#   node_modules/bin/obj/ocultos e repos filhos com .git).
param()
Write-Host '[OK] Migration 0.4.39-to-0.4.40 applied.'
