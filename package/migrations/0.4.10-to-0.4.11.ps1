#Requires -Version 5.1
# Migration 0.4.10 -> 0.4.11
# Runtime fixes (código, sem mudança de layout .orchestrator/) — transcrições PrintBee 2026-07-24:
# - REQUIRES_INPUT estruturado: executor bloqueado pausa em WAITING_FOR_USER sem queimar iteração;
#   pergunta repetida vira infra-reject + rotação de executor
# - Classificação: verbo de implementação vence keyword de análise (pedido "analisar e fazer mudanças"
#   não vira mais complex_analysis com ACs de auditoria)
# - Harness por stack: pytest só com marcador Python real (fim do pytest inventado em Angular);
#   prompts de executor/validator recebem os comandos de teste detectados
# - Cancel propaga kill para CLIs filhos; task barrada no lock ganha error "blocked_by_lock" visível
# - Timeout do executor sem arquivos alterados rejeita como infra e rotaciona executor (padrão
#   Codex/PowerShell no Windows); prompt orienta evitar heredoc/quoting PowerShell
# - Refino de plano com teto de 300s (SELECTING_AGENTS não fica preso no planner)
# - orchestrator_run avisa quando o MCP está stale vs disco
param()
Write-Host '[OK] Migration 0.4.10-to-0.4.11 applied.'
