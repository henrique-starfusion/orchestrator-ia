# Auditoria 2026-07-24 — Transcrições reais PrintBee → correções P0 do runtime (0.4.11)

Fontes obrigatórias analisadas:

- `docs/audits/2026-07-24-transcript-field-distribution.md` (chat "Field distribution improvements", Cursor 3.12.17)
- `docs/audits/2026-07-24-transcript-orchestrator-execution.md` (chat "Orchestrator execution analysis")
- `docs/audits/2026-07-23-printbee-process-orchestrator-improvements.md` (baseline 0.4.10 já aplicado, commit `0b2b21a`)
- Evidência local: `.orchestrator/runtime/results/` (tasks d511b77505a0, cbd3c5a230ba, 7684b598dced), SQLite `.orchestrator/data/orchestrator.db`, VERSION 0.4.10 no início da sessão

Contexto: MCP do Cursor estava stale em 0.4.8 enquanto a CLI/disco tinha 0.4.10. Os patches P0 de 0.4.10 (git timeout, `AGENT-EMPTY-OUTPUT`, validator infra≠mérito, delegate finaliza) **não** foram reimplementados — esta release cobre o que AINDA falhava nas transcrições.

---

## Achados e correções (F1–F6)

### F1 — Executor pergunta decisão de negócio em vez de implementar (P0 → CORRIGIDO em 0.4.11)

**Evidência (transcrição field-distribution):**
- Linhas 34–36: task `2de2a4d1e82f` — "O Codex parou pedindo definição de negócio"; "A 1ª execução não alterou arquivos (Codex pediu decisão de negócio). Vou cancelar e relançar".
- Linhas 207, 215: validator FluentValidation — "O Codex não escreveu o arquivo (perguntou em vez de implementar)".

**Causa no código:** `_build_executor_prompt` (`tasks/service.py`) não impunha escopo nem oferecia canal estruturado de pergunta; a iteração inteira era queimada e o chat cancelava a task.

**Correção (0.4.11):**
- Prompt do executor/corrector proíbe perguntas abertas quando o objetivo define o escopo e define o protocolo `REQUIRES_INPUT: {"question", "options"}` (`tasks/service.py:935-943`).
- Runtime detecta a linha estruturada quando não houve arquivos alterados: pausa em `WAITING_FOR_USER` **sem consumir a iteração**, expõe pergunta/opções em `orchestrator_status` (`tasks/service.py:481-536`; parser em `tasks/service.py:969-990`).
- `orchestrator_message` + resume reentra o pipeline via transição nova `WAITING_FOR_USER → ANALYZING` preservando a resposta do usuário (`tasks/state_machine.py:108-119`, `tasks/service.py:255-296`; a transição antiga de `message()` para PLANNING quebrava o resume — removida em `mcp/tools.py`).
- Pergunta repetida após resposta vira issue de infra `AGENT-REQUIRES-INPUT` com rotação de executor e stop por `same_issue_repeat_limit` (`tasks/service.py:516-536`).

### F2 — Classificação errada: implementação vira `complex_analysis`; fable preso em SELECTING_AGENTS (P0 → CORRIGIDO em 0.4.11)

**Evidência:**
- Transcrição field-distribution linhas 197–201: "critérios de aceite parecem de análise… A task ficou presa em SELECTING_AGENTS com critérios de análise (classificação errada). Vou cancelar e relançar"; linha 212: tasks `98bbbb0439b8` / `465aa89c0420` canceladas ("planner fable travava em SELECTING_AGENTS / classificação errada"); linha 189: task `8cc3bf79c533`.
- Código 0.4.10: `TaskAnalyzer.analyze` (`planning/analyzer.py`) classificava `complex_analysis` por substring ("analis", "audit"…) mesmo com verbo de implementação no mesmo prompt ("use o orquestrador para **analisar e fazer estas mudanças**"); `CriteriaBuilder` então gerava ACs de auditoria (EVIDENCE) em vez de `workspace_changes`.
- O refino de plano pelo planner rodava com orçamento de role (900s) segurando o status em SELECTING_AGENTS, embora o plano determinístico já existisse e o output do refino seja advisory (`tasks/service.py`, chamada do planner).

**Correção (0.4.11):**
- Verbo de implementação vence keyword de análise (`planning/analyzer.py:51-107`): lista `_IMPLEMENTATION_INTENT` + `\bfix\b`, com cláusulas negadas removidas antes do match (reusa `_NEGATED_CLAUSE_RE` — "não criar módulo soma" não vira intenção).
- Refino do planner com teto duro `PLANNER_REFINE_CAP_S = 300` (`tasks/service.py:49`, aplicado em `tasks/service.py:344` via `timeout_cap_s` de `_run_agent`). SELECTING_AGENTS nunca mais fica 15 min preso; o workflow segue com o plano determinístico.

### F3 — Fila/lock: task longa segura o lock, novas ficam RECEIVED mudas, cancel não mata filhos (P0 → CORRIGIDO em 0.4.11)

**Evidência:**
- Field-distribution linha 42: "A nova tarefa ficou em fila atrás de outra execução"; linha 48: relançamento `ae75632e65c8` "preso em RECEIVED atrás de outra tarefa"; linhas 120, 185: auditoria Istio `7ca502037bc6` "há horas em EXECUTING e bloqueia a fila… vou cancelá-la de novo"; linha 40: "Processos Codex da tarefa cancelada ainda vivos — vou encerrá-los para liberar a fila".
- Código 0.4.10: `run_task` com lock ocupado só emitia evento e devolvia a task RECEIVED sem nenhum campo persistido (`tasks/service.py`, handler de `TimeoutError`); `cancel()` só marcava `cancel_requested` — o CLI filho (Codex) continuava rodando. Recuperação de lock stale JÁ existia (`execution/locks.py:38-60`, PID morto/idade — 0.4.x).

**Correção (0.4.11):**
- Task barrada no lock grava `error = "blocked_by_lock: …"` persistido (visível em `orchestrator_status`/`task list`) e o erro é limpo quando a execução real começa (`tasks/service.py:190-196`, `264-268`).
- `cancel()` propaga kill: `CliExecutor` rastreia PIDs ativos e `kill_active()` mata as árvores (`agents/process.py:74-77` init, tracking no `run()`, `kill_active` em `agents/process.py:198-211`; chamada em `tasks/service.py:125-137`). Check extra de `cancel_requested` logo após o retorno do executor (`tasks/service.py:477-479`) evita rodar TESTING/VALIDATING de task cancelada.

### F4 — Harness de teste errado: pytest exigido em projeto Angular (P0 → CORRIGIDO em 0.4.11)

**Evidência:**
- Transcrição orchestrator-execution linhas 53, 90: task `50b62a0c7ff4` — "Validator … ainda tentou `pytest` em frontend Angular"; "Harness de teste errado na 1ª task (pytest em Angular)".
- Código 0.4.10: `TestDiscovery.discover` disparava pytest com `project_path.glob("**/test_*.py")` (varre `node_modules`) **ou** `tests/` existente mesmo sem nenhum `.py` (caso Angular com specs TS) — `testing/discovery.py`.

**Correção (0.4.11):**
- `_is_python_project` (`testing/discovery.py:21-36`): pytest só com marcador real (pyproject/setup.py/setup.cfg/requirements.txt, `tests/` com `.py`, ou `test_*.py` na raiz). Sem varredura profunda.
- `stack_test_commands` (`testing/discovery.py:76-80`) injeta os comandos detectados nos prompts do executor (`tasks/service.py:943`, via `_stack_hint` em `tasks/service.py:955-967`) e do validator (`tasks/service.py:1004`): "Use SOMENTE estes comandos de teste; não exija outros (ex.: pytest em projeto Node/Angular)".

### F5 — Codex frágil no Windows (PowerShell quoting/heredoc) → timeout sem arquivos (P0 → MITIGADO em 0.4.11)

**Evidência:**
- Orchestrator-execution linhas 47–56: task `50b62a0c7ff4` — executor Codex "timeout (~10 min) — leu skills, quebrou em PowerShell/quoting, zero arquivos"; corrector "timeout de novo — mesma falha"; parou por `same_issue_repeat_limit`.
- Field-distribution linha 187: "O Codex está há ~15 min sem gerar arquivos. Vou relançar com executor Claude".
- Evidência local: `.orchestrator/runtime/results/d511b77505a0/validator-codex.txt:24-28` — `CreateProcessAsUserW failed: 740` disparado exatamente por comando PowerShell composto do Codex (o parse infra≠mérito disso já entrou em 0.4.10).

**Correção (0.4.11):**
- Timeout do executor com ZERO arquivos alterados vira issue de infra `AGENT-TIMEOUT-NO-OUTPUT` com **rotação automática de executor** via fallback (Codex→Claude) em vez do fluxo "continue do disco" — que era inútil sem arquivos (`tasks/service.py:588-609`). Timeout COM arquivos mantém o fluxo AGENT-TIMEOUT de 0.4.10 (retomar do disco).
- Prompt no Windows orienta: sem heredoc/quoting complexo de PowerShell; preferir tools de escrita do agente, `python -c` ou arquivo temporário (`tasks/service.py:944-949`).
- Preferência operacional: neste host, usar Claude como executor quando o Codex degradar — a rotação agora acontece sozinha na 1ª iteração perdida, e `role_model_preferences`/fallbacks em `models.json` continuam sendo o lugar para inverter a ordem por padrão (P1 abaixo).

### F6 — Processo MCP stale + bypass do chat (documentado; aviso novo em 0.4.11)

**Evidência:**
- Orchestrator-execution linhas 1830-1853: "O MCP desta sessão ainda está stale (0.4.8, modules_stale=true)"; todo o histórico 0.4.5→0.4.10 repete "recarregue o MCP".
- Bypass do chat já tratado em 0.4.7 (rules default), 0.4.9 (docstrings MCP DEFAULT) — sem regressão observada nas rules; o problema restante das transcrições é o processo stale mascarando os fixes.

**Correção (0.4.11):**
- `orchestrator_run` devolve `warnings: ["mcp_modules_stale"]` + aviso na mensagem quando o código carregado difere do disco (`mcp/tools.py:541-560`) — o chat fica sabendo NA HORA de despachar, não só no health.
- Fingerprint de stale passou a cobrir os módulos onde o comportamento do workflow vive: `tasks/service.py`, `tasks/state_machine.py`, `testing/discovery.py`, `agents/process.py` (`diagnostics.py:10-21`); features 0.4.11 adicionadas (`diagnostics.py:31-40`).
- Operacional (não corrigível por código): reload do MCP/Cursor continua obrigatório após update — agora sinalizado no próprio `orchestrator_run`.

---

## O que JÁ estava em 0.4.10 (não reimplementado)

| Item | Onde |
|---|---|
| Git `status`/`rev-parse` com timeout 30s (anti-hang RECEIVED) | `execution/git_workspace.py` |
| `AGENT-EMPTY-OUTPUT` + `_reject_iteration_infra` (stdout 2 bytes ≠ rejeição de AC) | `tasks/service.py` (evidência: `results/d511b77505a0/executor-claude.txt` e `corrector-claude.txt` com 2 bytes) |
| Validator infra (erro 740) ≠ mérito + fallback de validator | `validation/deterministic.py`, `tasks/service.py:880-908` (evidência: `results/d511b77505a0/validator-codex.txt:24-28`) |
| `orchestrator_delegate` finaliza task (fim dos órfãos RECEIVED) | `mcp/tools.py`, `tasks/state_machine.py` |
| Stale lock recovery (PID morto / idade) | `execution/locks.py:38-60` |

## Novo em 0.4.11 (esta release)

| Fix | Arquivos | Testes |
|---|---|---|
| REQUIRES_INPUT estruturado (pausa/resume/repeat) | `tasks/service.py`, `tasks/state_machine.py`, `mcp/tools.py` | `test_transcript_p0_fixes.py::test_requires_input_*`, `::test_state_machine_allows_requires_input_flow`; `test_mcp_tools.py::test_mcp_message` ajustado |
| Classificação: impl vence análise | `planning/analyzer.py` | `::test_implementation_verb_overrides_analysis_keyword`, `::test_pure_analysis_still_complex_analysis`, `::test_audit_with_recommendations_stays_analysis`, `::test_implementation_criteria_not_audit_criteria` |
| Teto 300s no refino do planner | `tasks/service.py` | `::test_planner_refine_capped_at_5_minutes` |
| Harness por stack + hint nos prompts | `testing/discovery.py`, `tasks/service.py` | `::test_no_pytest_for_node_project`, `::test_pytest_kept_for_python_project`, `::test_stack_hint_in_prompts` |
| Cancel mata filhos + lock visível | `agents/process.py`, `tasks/service.py` | `::test_cancel_kills_active_child_processes`, `::test_cli_executor_tracks_and_kills_active_pids`, `::test_cli_executor_clears_pid_after_run`, `::test_blocked_by_lock_*` |
| Timeout sem output → rotação | `tasks/service.py` | `::test_timeout_without_output_rotates_and_stops` |
| Aviso MCP stale no run + fingerprint ampliado | `mcp/tools.py`, `diagnostics.py` | cobertura existente `test_diagnostics.py` (shape) |

Release: VERSION/package.json/runtime pyproject/`__init__`/template = **0.4.11**; CHANGELOG atualizado; migration `package/migrations/0.4.10-to-0.4.11.ps1`; checksum de `template/.orchestrator/VERSION` atualizado em `package/checksums.json` (sha256 `07ce142af9edc614…`).

## Execução de testes (evidência)

Sessão autônoma com gate de permissão: `pytest`/`python -m py_compile`/`npm` **negados** (mesmo padrão das sessões de 0.4.7–0.4.10; ver `.wolf/STATUS.md`). Verificação feita estaticamente (trace das transições e dos fluxos dos 17 testes novos). **Rodar em sessão interativa:**

```bash
npm run test:runtime          # inclui runtime/tests/unit/test_transcript_p0_fixes.py (17 casos novos)
npm test                      # 26 suítes PowerShell
```

Depois: commit/push develop, `orchestrator update -Force` em printbee/bootstrap-agents/GuardLine, **reload do MCP** (agora o próprio `orchestrator_run` avisa se esquecer).

## Recomendações P1 (documentadas, não implementadas)

1. **Executor default por host**: em `models.json`/policies, permitir `executor_preference_order` por host — neste Windows, Claude antes de Codex (a rotação 0.4.11 corrige por iteração; a preferência evitaria a 1ª iteração perdida).
2. **Fila explícita**: task com lock ocupado poderia entrar em estado `QUEUED` com posição, em vez de RECEIVED+error; exigiria estado novo na máquina e UI.
3. **Truncar artefatos grandes** em `runtime/results/` (pendente de 0.4.10).
4. **Orçamento multi-iteração maior** para tasks longas (pendente de 0.4.10).
5. **Watchdog de EXECUTING**: task acima de N× o timeout da role sem evento novo → marcar STALLED e liberar lock (o caso Istio "horas em EXECUTING" sugere processo morto sem cleanup; o stale-lock recovery só age com PID morto).
6. **Delegate com regra anti-pergunta**: `orchestrator_delegate` envia o objective cru; aplicar o mesmo bloco de escopo/REQUIRES_INPUT do executor.
