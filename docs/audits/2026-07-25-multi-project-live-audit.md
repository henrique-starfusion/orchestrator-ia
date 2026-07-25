# Auditoria ao vivo — projetos com Orchestrator (0.4.23)

**Data:** 2026-07-25 ~18:40 UTC-3  
**Método:** leitura direta do registry + SQLite RO + `models.json` / `legacy-import` (acesso pleno; não via MCP).  
**JSON bruto:** `.orchestrator/runtime/reports/multi-project-usage-2026-07-25.json`  
**Nota:** MCP Cursor ainda **stale** (processo 0.4.19 vs disco 0.4.23) — afeta sessões IDE, não esta leitura de disco.

## 1. Sumário

| Sinal | Valor |
|---|---|
| Projetos reais no registry | 10 (todos em **0.4.23**) |
| Entradas lixo Temp no registry | **40** (todas path missing) |
| Uso real (DB com tasks) | **4/10**: bootstrap, printbee, GuardLine, adzora |
| Só template (sem DB) | **6/10**: corehub, gangsheeter, rivero, starfusion, ukomerce, vavi |
| Tasks ativas agora | **0** (nenhum lock `workspace.write.lock`) |
| Fila QUEUED exercida | **0** eventos/tasks nos DBs |

Taxas de conclusão (tasks no DB):

| Projeto | Tasks | COMPLETED | CANCELLED | INCOMPLETE | FAILED |
|---|---:|---:|---:|---:|---:|
| printbee | 51 | 3 (6%) | 41 (80%) | 5 | 2 |
| bootstrap-agents | 25 | 2 (8%) | 11 (44%) | 9 | 3 |
| GuardLine.BR | 3 | 0 | 3 (100%) | 0 | 0 |
| adzora | 3 | 0 | 1 | 1 | 1 |

**Conclusão operacional:** o orquestrador está instalado em massa, mas **só PrintBee + bootstrap** o usam de verdade — e o funil morre em cancel/incomplete.

## 2. Como cada projeto está

### Uso alto

- **printbee** — 51 tasks (28 implementation). Product work real (regras de produção, product-picker, prazos). Legacy-import rico (15 cursor rules, 88 arquivos em skills). Models 0.4.21+ ok (executor opus / validator sonnet).
- **bootstrap-agents** — dogfooding do pacote (releases, filas, auditorias). Mesmo routing ok. Completou 2 implementations (`4c049e25f09e` Codex sandbox entre elas).

### Uso baixo / falho

- **GuardLine.BR** — 3 tasks, 100% CANCELLED. Um erro `CANCELLED -> TESTING` (zumbi pós-cancel).
- **adzora** — 3 tasks; `FAILED`/`INCOMPLETE` por `[WinError 2] O sistema não pode encontrar o arquivo especificado` (CLI/path do agente). `planner` prefs ausentes no `models.json` (só executor/validator do patch 0.4.22).

### Sem runtime

- corehub, gangsheeter, rivero, starfusion, ukomerce, vavi — MCP + template + legacy-import, **zero** `orchestrator.db`. Instalados, não exercitados.

## 3. Falhas recorrentes (evidência DB)

1. **Cancel sem motivo persistido** — printbee 35/41 cancels sem `error`; bootstrap 9. Domina o funil.
2. **`Transição inválida: CANCELLED -> TESTING`** — printbee×6, bootstrap×2, GuardLine×1 → **bug-022 ainda vivo** (loop continua após cancel).
3. **`EXECUTING -> RETRIEVING_MEMORY`** inválida — printbee×2 (reentrada de fase).
4. **`RETRIEVING_MEMORY -> RETRIEVING_MEMORY`** — bootstrap (same-state deveria ser no-op desde 0.4.16; ainda aparece como FAILED).
5. **WinError 2** — bootstrap + adzora (binário/agente não encontrado no spawn).
6. **Timeout de orçamento** — bootstrap `maximum_duration` em INCOMPLETE.
7. **Fila 0.4.19** — nunca usada nos DBs reais (0 menções a QUEUED).

## 4. Ajustes recomendados no orquestrador (priorizados)

### P0 — confiabilidade do cancel / loop

| ID | Ajuste | Por quê |
|---|---|---|
| A1 | **Hard-stop do loop** ao `cancel_requested` / estado terminal (não só kill CLI) | `CANCELLED -> TESTING` ainda aparece em produção |
| A2 | Recusar qualquer `assert_transition` saindo de CANCELLED/FAILED/COMPLETED/INCOMPLETE | Elimina zumbis que seguram lock |
| A3 | Persistir `cancel_reason` (MCP/CLI/user) no campo `error` ou coluna dedicada | Hoje 80%+ dos cancels são opacos |

### P0 — fricção que força “cancela e faz inline”

| ID | Ajuste | Por quê |
|---|---|---|
| A4 | **Reload/fingerprint gate** no MCP: se `modules_stale`, `orchestrator_run` falha cedo com mensagem clara | Sessões IDE ainda em 0.4.19 enquanto disco é 0.4.23; planner/executor errados e hangs |
| A5 | Fail-fast em SELECTING_AGENTS / skill_selector > N s sem progresso | Histórico de “travou em SELECTING_AGENTS” no PrintBee |
| A6 | Alinhar rules: `git-workflow` não deve incentivar commit inline enquanto houver task ativa | Ritual cancel+inline anula o runtime |

### P1 — agentes / spawn Windows

| ID | Ajuste | Por quê |
|---|---|---|
| A7 | Diagnosticar e surfacear WinError 2 (path resolvido + `where.exe` no erro da task) | adzora e bootstrap falharam opacos |
| A8 | Probe de agentes no primeiro `run` do projeto (não só no install) | 6 projetos nunca rodaram; quando rodarem, surpresas de PATH |

### P1 — registry / hygiene

| ID | Ajuste | Por quê |
|---|---|---|
| A9 | **Prune** automático de entradas Temp/`orchestrator-tests-*` ausentes no registry | 40 stubs poluem propagate |
| A10 | Não registrar projetos de teste (`New-TestProjectDirectory`) no registry global | Causa raiz do A9 |

### P2 — valor do import / adoção

| ID | Ajuste | Por quê |
|---|---|---|
| A11 | Promoção assistida `legacy-import` → skills/rules ativas (ou índice no skill selector destacando imports) | PrintBee tem 88 arquivos importados; risco de ficarem “requires-review” para sempre |
| A12 | Onboarding no primeiro `orchestrator_run` em projeto sem DB (smoke task opcional) | 6/10 só template |
| A13 | Garantir `role_model_preferences.planner` no patch de models (adzora/outros sem planner no JSON) | Defaults do runtime cobrem, mas JSON inconsistente |

### P2 — fila

| ID | Ajuste | Por quê |
|---|---|---|
| A14 | Telemetria/evento explícito quando enfileira; doc + teste e2e com 2 runs paralelos no mesmo workspace | Feature 0.4.19 nunca apareceu nos DBs |

## 5. O que já está bem

- Versões homogeneizadas em **0.4.23** nos 10 projetos reais.
- Routing de modelos (executor opus / validator sonnet) presente onde o patch rodou.
- Import 0.4.23 funcionou (PrintBee cursor rules=15; GuardLine/adzora com legacy-import).
- Nenhum lock zumbi no momento da varredura.
- Codex fail-fast / sandbox Windows já no código (efeito em produção ainda misturado com cancels).

## 6. Próximo passo sugerido

1. Recarregar MCP (obrigatório antes de qualquer `orchestrator_run` confiável).  
2. Implementar **A1+A2+A3** (cancel hard-stop) como 0.4.24.  
3. **A9+A10** (prune registry) no mesmo release — baixo risco, alto higiene.  
4. Só depois atacar A4/A5 (UX MCP stale + SELECTING hang).
