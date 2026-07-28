#Requires -Version 5.1
# Migration 0.4.37 -> 0.4.38
# Terceira rodada GuardLine.BR (parte 2) — tudo em codigo do runtime:
# - bug-051: criterios EVIDENCE/CUSTOM inverificaveis nao reprovam mais no det
#   (satisfied=None; o validador LLM julga) — fim do veto "prefer stricter"
#   sobre aprovacao 1.0 em task re-executada sobre entrega existente.
# - bug-052: same_issue_repeat conta por id + descricao normalizada (ids sao
#   posicionais; problemas diferentes com o mesmo id nao repetem).
# - bug-053: validator==executor pos-rotacao gira o validator para fallback
#   disponivel antes de bloquear com VAL-IND.
# - bug-054: descoberta Go roda `go test -short ./...` (testing.Short() pula
#   testes live/rede/mTLS que falham offline).
param()
Write-Host '[OK] Migration 0.4.37-to-0.4.38 applied.'
