# Ciclo 6 — revisão do comportamento da última análise (2026-07-21)

## O que a análise anterior mostrou (comportamento)

Na auditoria via `orchestrator_analyze` sobre o 0.4.1:

1. **Requirements partidos** — `re.split` em `.` transformava `0.4.1` em  
   `"Auditoria … orquestrador 0"` + `"1: gaps…"`.
2. **task_type errado** — “Auditoria” não batia em `analis*`, caía em `implementation`.
3. **ACs genéricos de produto** — default pedia README + testes mesmo para auditoria read-only.
4. **Agente Cursor** — implementou ciclos 5/6 úteis, mas **não fechou** o bug de parse que o próprio `analyze` já evidenciava na resposta.

## Ajustes feitos

| Problema | Correção |
|----------|----------|
| Split semver | `extract_requirements()` com `(?<!\d)\.(?!\d)` |
| Auditoria → implementation | keywords `auditor`/`audit`/`gap` → `complex_analysis` |
| ACs de README em audit | defaults `EVIDENCE`/`WORKSPACE_CHANGES` para analysis/security/architecture |
| Feedback opaco | `analyze` devolve `message` + `warnings` (ex.: independent_validation_ok) |
| Doc ciclo 5 desatualizada | este arquivo registra o follow-up |

## Como o agente deve se comportar daqui pra frente

1. Se `orchestrator_analyze` devolver requirements estranhos → **tratar como bug**, não seguir o plano cego.
2. Para auditorias: esperar `task_type=complex_analysis` e ACs `evidence`, não demo soma/README.
3. Após fix de runtime MCP: **reload Cursor** antes de revalidar tools.
