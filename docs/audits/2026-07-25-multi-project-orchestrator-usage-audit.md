# Auditoria — Uso do Orchestrator nos projetos instalados (0.4.20)

**Data:** 2026-07-25
**Task:** 9d80c6ee4730 (complex_analysis, sessão autônoma inline, `ORCHESTRATOR_CHILD_AGENT=1`)
**Escopo:** 10 projetos registrados no registry `%LOCALAPPDATA%\StarFusion\orchestrator\projects.json`

## Nota de método (limitação de acesso)

O sandbox desta sessão autônoma restringe leitura a `D:\StarFusion\bootstrap-agents` — **todas** as vias (Read, Glob, `cat`, `ls`, PowerShell `Get-Content`) foram negadas para o registry em `%LOCALAPPDATA%` e para os outros 9 projetos (erros literais: "Claude Code may only access files in the allowed working directories"). `sqlite3`, `git` e `python` exigem aprovação interativa (bloqueados). Mesma limitação da auditoria 2026-07-24 (`docs/audits/2026-07-24-conversation-orchestrator-usage-audit.md`).

A matriz foi reconstruída de **artefatos duráveis dentro do workspace**:

- `.orchestrator/runtime/reports/propagate-update.json` (2026-07-25T17:48:55Z) — execução real do propagate 0.4.20 sobre os 10 projetos do registry, com versão `from`/`to` de cada um;
- `.orchestrator/runtime/reports/installation-report.md` (2026-07-25 14:47) — update 0.4.20 do workspace canônico;
- `.orchestrator/data/orchestrator.db` local (1.458.176 bytes, mtime 2026-07-25 14:56) — extraído com `tr -d '\000' | grep` (sem exec de sqlite);
- `.orchestrator/runtime/tmp_pb_tasks.json` (dump de `orchestrator task` rodado em `D:\StarFusion\printbee` em 2026-07-24 ~20:54, 33 tasks) + `tmp_pb_task535_events.json`;
- `.wolf/buglog.json`, `.orchestrator/memory/learnings/`, auditorias anteriores em `docs/audits/`;
- Snapshot do registry fornecido no enunciado da task (paths, `db=sim/não`), cruzado com o propagate-update.json (listas idênticas — consistente).

Contagens de DB dos projetos remotos (printbee, GuardLine, adzora) vêm de snapshots de 2026-07-24; podem ter mudado desde então. Reexecução com acesso pleno recomendada (ver R7 da auditoria anterior, ainda pendente).

## 1. Sumário executivo

- **Versões: OK.** Os 10 projetos estão em 0.4.20. O propagate novo (0.4.20, `bin/orchestrator.js` + `scripts/Propagate-OrchestratorUpdate.ps1`) funcionou na primeira execução real: 8 projetos já estavam atuais, GuardLine.BR foi atualizado 0.4.19 → 0.4.20 automaticamente (`propagate-update.json`).
- **Uso real: concentrado em 2 de 10 projetos.** bootstrap-agents (24 tasks com eventos no DB) e printbee (33 tasks no snapshot) concentram ~95% do uso. GuardLine tem DB mas pouquíssimo uso (1 task conhecida, CANCELLED). adzora tem DB sem evidência de task. **6 projetos (corehub, gangsheeter, rivero, starfusion, ukomerce, vavi) não têm `data/orchestrator.db` — o runtime nunca rodou: instalação é só template.**
- **Taxa de conclusão muito baixa.** bootstrap-agents: 2 COMPLETED em 24 tasks (8%); eventos terminais: 19 CANCELLED / 8 INCOMPLETE / 5 FAILED / 2 COMPLETED. printbee: 21 CANCELLED em 33 (64%), 3 COMPLETED (9%). O padrão dominante é **cancelar pelo chat e terminar inline** (documentado também na auditoria de 24/07).
- **bug-022 (cancel não mata o loop) segue ABERTO e é o defeito mais grave**: o DB local registra 34 transições terminais para apenas 24 tasks — tasks canceladas continuam transicionando (5 casos reproduzidos abaixo), inclusive segurando `workspace.write.lock`.
- Correções 0.4.15/0.4.16 (Codex 740 fail-fast, same-state no-op, single-flight lock, stale RECEIVED TTL) estão no código e endereçam causas conhecidas; a fila 0.4.19 nunca foi exercida no DB local (0 transições para QUEUED).

## 2. Matriz por projeto

Fontes: [P] = propagate-update.json 2026-07-25; [R] = registry snapshot do enunciado; [DB] = orchestrator.db local; [PB] = tmp_pb_tasks.json 2026-07-24; [A24] = docs/audits/2026-07-24-transcript-orchestrator-execution.md.

| Projeto | Versão | DB? | #Tasks | Cancel% | Fail% | Completed% | Uso real |
|---|---|---|---|---|---|---|---|
| D:\StarFusion\bootstrap-agents | 0.4.20 [P] | sim (1,46 MB) [DB] | 24 c/ eventos | 79% das tasks têm evento de cancel (19/24) | 21% (5/24) | 8% (2/24) | **Alto** (dogfooding do pacote) |
| D:\StarFusion\printbee | 0.4.20 [P] | sim [R][PB] | 33 (snapshot 24/07) | 64% (21/33) | 0% | 9% (3/33) | **Alto** (features reais: Baileys/menções, regras de produção, vendas) |
| D:\GuardLine.BR | 0.4.20 (0.4.19 até 25/07 14:48) [P] | sim [R] | ≥2 conhecidas (79939e882328 CANCELLED 22/07; 85ff56f1f7da cancelada; órfã 76ca733d9794) [A24] | ~100% conhecido | — | 0% conhecido | **Baixo** |
| D:\StarFusion\adzora | 0.4.20 [P] | sim [R] | sem evidência no workspace | — | — | — | **Baixo/desconhecido** (DB existe ⇒ runtime já iniciou ao menos 1×) |
| D:\StarFusion\corehub | 0.4.20 [P] | não [R] | 0 | — | — | — | **Nenhum** (só template) |
| D:\StarFusion\gangsheeter | 0.4.20 [P] | não [R] | 0 | — | — | — | **Nenhum** (só template) |
| D:\StarFusion\rivero | 0.4.20 [P] | não [R] | 0 | — | — | — | **Nenhum** (só template) |
| D:\StarFusion\starfusion | 0.4.20 [P] | não [R] | 0 | — | — | — | **Nenhum** (só template) |
| D:\StarFusion\ukomerce | 0.4.20 [P] | não [R] | 0 | — | — | — | **Nenhum** (só template) |
| D:\StarFusion\vavi | 0.4.20 [P] | não [R] | 0 | — | — | — | **Nenhum** (só template) |

Detalhe bootstrap-agents (eventos `state_changed` no DB local): `to CANCELLED`=19, `to INCOMPLETE`=8, `to FAILED`=5, `to COMPLETED`=2 (34 desfechos terminais para 24 task ids distintos — ver achado P0-1). COMPLETED: `8ee2662ba984` (24/07 12:30) e `4c049e25f09e` (24/07 18:39).

Detalhe printbee (snapshot 24/07 20:54, 33 tasks): 21 CANCELLED, 3 COMPLETED (`fcd65612e8b1` architecture, `f5bb7269c880`, `8aae2e2e6e74` implementation), 3 INCOMPLETE, 5 paradas em RECEIVED (`9f212da731fa`, `1fae92413592`, `fbd6c2804f0b`, `c732b0bf7143`, `e0cc8c6459bb`), 1 RETRIEVING_MEMORY. Tipos: implementation (maioria), complex_analysis, architecture, docs.

Config/agentes (bootstrap-agents, válido como referência do template distribuído):
- `.orchestrator/config/policies.json`: `maximum_iterations=3`, `minimum_validation_score=0.9`, `maximum_duration_seconds=3600`, `agent_infra_fail_fast_count=3` (0.4.15), `stale_received_ttl_hours=6` (0.4.16), token_economy + required_agent_tooling (OpenWolf/Graphify/Superpowers/Caveman).
- `.orchestrator/agents/detected.json` (2026-07-25 14:47): disponíveis claude 2.1.219, codex-cli 0.145.0, kimi 0.29.0, opencode 1.18.4, cursor (IDE); 15 outros not_installed.
- `.cursor/mcp.json`: servidor `orchestrator-ia` via `cmd /c orchestrator mcp serve --transport stdio --project ${workspaceFolder}`.
- Perfil típico de plano (dump printbee): `planner=claude, executor=codex, validator=claude`, fallbacks executor `[claude, opencode]`, validator `[codex, opencode]`, planner `[opencode, kimi]`, estratégia `execute_review_repair`.

## 3. Achados

### P0-1 — bug-022 ABERTO: cancel não encerra o loop; tasks zumbis re-transicionam e seguram o write lock

**Evidência (DB local, eventos `state_changed`):** 34 transições terminais para 24 tasks distintas. Casos reproduzidos:

| Task | Cancel persistido | Transições DEPOIS do cancel |
|---|---|---|
| `d511b77505a0` | VALIDATING→CANCELLED 2026-07-24T00:20:37Z | VALIDATING→INCOMPLETE 00:20:48Z |
| `13c2d4baf8d7` | VALIDATING→CANCELLED 16:59:21Z | VALIDATING→INCOMPLETE 17:27:10Z (28 min zumbi) |
| `74626c2e4da0` | VALIDATING→CANCELLED 17:27:08Z | VALIDATING→INCOMPLETE 17:48:13Z (iter=2 zumbi) |
| `901c73f6be86` | RECEIVED→CANCELLED 18:39:51Z | VALIDATING→CORRECTING 19:09:46Z; CORRECTING→INCOMPLETE por `maximum_duration_seconds` ("Orçamento de tempo esgotado") |
| `2be223ce5511` | RECEIVED→CANCELLED 22:01:13Z | SELECTING_AGENTS→EXECUTING 22:06:22Z |

`.wolf/buglog.json` bug-022: "ABERTO", causa suspeita = loop em memória re-salva transições sobrescrevendo estado terminal; `kill_active` pode matar CLIs sem parar o loop. Lock atual: `.orchestrator/runtime/locks/workspace.write.lock` presente (pid 31616 — task corrente, legítimo; mas o mesmo mecanismo foi segurado por zumbi 74626 em 24/07).

**Impacto:** cancel é a ação mais usada (19 eventos em bootstrap, 21 tasks em printbee) e não é confiável — consome tokens/tempo depois do cancel, bloqueia o workspace e corrompe a semântica de estado terminal.

### P0-2 — Padrão "cancela e faz inline pelo chat" domina o funil e anula o valor do orquestrador

**Evidência:**
- printbee: 64% CANCELLED. A sequência das 20:22–20:54 de 24/07 mostra o ritual: `589c6c4a876b` "travou em SELECTING_AGENTS e foi cancelada; **o agente Cursor aplicou o fix manualmente**" (texto literal no prompt da task seguinte `019e616ef02f`, em `tmp_pb_tasks.json`); depois 4 reenvios do mesmo review (`019e616ef02f` 20:45, `76e6c0edcfbb` 20:48, `858639e9dadb` 20:50, `535daf06a601` 20:54), os 3 primeiros cancelados 2–3 min após criação.
- Auditoria 2026-07-24 (conversation-usage): releases 0.4.12/13/14 canceladas em EXECUTING/VALIDATING e commitadas inline 2min/37s/11s após o cancel; commit inline zera o diff e fabrica rejeições falsas de AC (`changed_files_since` vazio).
- Conflito de rules: `.cursor/rules/multiagent-orchestrator.mdc` impõe `orchestrator_run` como default obrigatório ("bug fix NUNCA é exceção"), enquanto `.cursor/rules/git-workflow.mdc:20-27` manda o chat commitar+push ao concluir — o chat vira o finalizador natural de toda task cancelada.

**Impacto:** o orquestrador paga o custo de planner/executor e o chat colhe o resultado; métricas de validação ficam sem sentido; aprendizado (learnings) registra falha para trabalho que na verdade foi entregue.

### P1-1 — Hangs do Codex no Windows (erro 740) induziram os cancels em VALIDATING; fix 0.4.15 no código, eficácia ainda não medida

**Atualização (2ª iteração, 25/07):** eficácia parcialmente comprovada em produção nesta própria task — ver §7: fail-fast matou o Codex em 3 ocorrências, mas Codex continua inutilizável como validator no Windows.

**Evidência:** `.wolf/buglog.json` bug-023: `CreateProcessAsUserW failed: 740` com `--sandbox workspace-write`; Codex não aborta, entra em loop `node_repl/js`; runtime esperava timeout de 1800s. "Evidencia em results/74626c2e4da0/validator-codex.txt e 5e18b4339f22/validator-codex.txt" (os diretórios `results/` antigos foram removidos pelo legacy-cleanup de 25/07 — só resta `results/9d80c6ee4730/` da task corrente; a citação do buglog é o registro durável). Fix 0.4.15 presente no código: `runtime/src/orchestrator_runtime/agents/process.py` (INFRA_FAIL_MARKERS + fail-fast) e `agents/base_adapters.py` (override `workspace-write→danger-full-access` em Windows); `policies.json: agent_infra_fail_fast_count=3`.

**Impacto residual:** todos os cancels em VALIDATING de 23–24/07 antecedem ou coincidem com o fix; não há nenhuma task pós-0.4.15/0.4.20 completada que comprove que VALIDATING deixou de arrastar. Sem essa comprovação, o gatilho comportamental do P0-2 continua armado.

### P1-2 — MCP stale: processo `mcp serve` reporta versão antiga (0.4.19) enquanto o disco já está em 0.4.20

**Evidência:** disco atualizado 2026-07-25 14:46 (`.orchestrator/VERSION` mtime) e propagate 14:48; qualquer processo MCP iniciado antes disso serve a versão anterior — exatamente o padrão recorrente já documentado: `docs/audits/2026-07-24-transcript-orchestrator-execution.md:278` ("processos `python -m orchestrator_runtime mcp serve` ainda reportam version=0.4.4. CLI já está em 0.4.5"), repetido em 0.4.12/0.4.13 (`docs/audits/2026-07-24-0.4.14-learn-then-compact-verification.md:59`) e agora com health reportando 0.4.19 vs 0.4.20 no disco (relato do operador no enunciado desta task). `docs/troubleshooting.md:50` já tem seção 0.4.20 sobre esquecer consumidores.

**Impacto:** fila 0.4.19, propagate 0.4.20 e fixes 0.4.15/16 só valem após reload do MCP em CADA workspace aberto no Cursor; health enganoso mascara isso.

### P1-3 — 6 de 10 projetos são instalação "só template": nunca rodaram o runtime

**Evidência:** registry marca `db=não` para corehub, gangsheeter, rivero, starfusion, ukomerce e vavi (ausência de `.orchestrator/data/orchestrator.db` = runtime jamais inicializou); o propagate de 25/07 confirma que todos têm `.orchestrator/VERSION` 0.4.20 válido (logo a instalação existe e é mantida).

**Impacto:** custo de manutenção (propagate, migrations, backups) sem nenhum retorno; 60% da frota não valida nenhuma release. Ou faltou onboarding (rules/mcp.json nos projetos? MCP não configurado no Cursor desses workspaces?) ou os projetos não têm demanda — decisão de produto necessária.

### P1-4 — `discover_roots` não inclui `D:\GuardLine`: GuardLine só é alcançado enquanto a entrada do registry existir

**Evidência:** `scripts/Orchestrator.Common.ps1:971` e `:991` — default `discover_roots = @('D:\StarFusion')`; `:979-980` injeta o mesmo default se o campo faltar. `scripts/Propagate-OrchestratorUpdate.ps1:35` itera `reg.discover_roots` para descoberta. GuardLine.BR está fora de `D:\StarFusion`; hoje é atualizado porque está registrado explicitamente, mas um reset/corrupção do `projects.json` (arquivo novo de 0.4.20, sem backup conhecido) faria o `--discover` reconstruir a frota **sem** GuardLine.

### P2-1 — Fila 0.4.19 nunca exercida; órfãs RECEIVED ainda eram o modo de falha no printbee

**Evidência:** DB local: 0 eventos `"to": "QUEUED"` (grep binário). Snapshot printbee 24/07: 5 tasks paradas em RECEIVED (criadas 24/07 00:23–20:54) — padrão pré-fila que o `stale_received_ttl_hours=6` (0.4.16) deveria varrer no próximo `create_task`. Nenhuma evidência durável de dequeue automático funcionando em produção.

### P2-2 — bug-025 derrubou task por transição same-state (corrigido 0.4.16, confirmado no DB)

**Evidência:** evento no DB local: `db98d0f627b1` 2026-07-24T21:01:45Z `RETRIEVING_MEMORY→FAILED`, error "Transição inválida: RETRIEVING_MEMORY -> RETRIEVING_MEMORY". Fix em `tasks/state_machine.py` + `tasks/repository.py` (same-state no-op). Falha de infra contaminando métrica de fail%.

### P2-3 — Aprendizado durável cobre só 17% das tasks

**Evidência:** `.orchestrator/memory/learnings/` contém 4 arquivos (`1309dd769575`, `2be223ce5511`, `3e7959383262`, `db98d0f627b1`) para 24 tasks com eventos. Tasks canceladas cedo (maioria) não deixam learning — exatamente as que mais precisariam registrar "por que cancelou".

### P2-4 — Working tree do pacote com `bin/orchestrator.js` modificado após a release 0.4.20

**Evidência:** git status no início desta sessão: `M bin/orchestrator.js` sobre o commit de release `992970c release: 0.4.20`. Mudança do próprio propagate fora do commit da release ⇒ o que foi propagado aos projetos pode divergir do que está versionado.

## 4. Como o orquestrador está sendo usado (padrões)

1. **Dois modos reais:** (a) bootstrap-agents usa o orquestrador para evoluir o próprio orquestrador (releases, auditorias, fixes) — dogfooding; (b) printbee usa para features/bugs de produto (menções WhatsApp/Baileys, regras de produção, toggles de venda) com prompts ricos, ACs e "Sem commit/push" explícito. Os demais projetos não usam.
2. **Rules empurram tudo para o orquestrador:** `multiagent-orchestrator.mdc` (alwaysApply) torna `orchestrator_run` default obrigatório, com anti-padrões explícitos contra fix inline e contra subagentes Task do Cursor.
3. **Perfil de agentes homogêneo:** planner=claude, executor=codex, validator=claude, profile balanced, `execute_review_repair` — em praticamente todas as tasks do dump printbee.
4. **Ritual dominante de falha:** task trava (SELECTING_AGENTS/VALIDATING, historicamente por Codex 740 e MCP stale) → operador cancela pelo chat → chat implementa inline → às vezes reenvia a task como "review do diff já aplicado" (série 019e/76e6/858639/535daf) — que também é cancelada. O orquestrador vira gerador de plano/registro, não executor.
5. **Enforcement de agente filho funciona:** esta task rodou com `ORCHESTRATOR_CHILD_AGENT=1`; `agents/process.py:108-115` bloqueia delegação aninhada e `tasks/service.py:1199-1204` injeta o bloco INLINE no prompt do executor — auditoria executada 100% inline, sem hang.
6. **Higiene automática ativa:** backups pre-update/legacy-cleanup a cada update (63 pastas em `.orchestrator/backups/`), installation-report e agora propagate-update.json como trilha de auditoria.

## 5. Recomendações priorizadas

**Quick wins (dias):**
1. **[P0] Corrigir bug-022 (cancel zumbi):** no loop de execução, revalidar estado persistido antes de cada `transition()`/re-save e abortar se terminal; garantir que `cancel()` sinalize o loop em memória (evento/flag observado pelo runner), não só o DB. Teste de regressão: cancelar em VALIDATING e afirmar ausência de eventos posteriores. (Já especificado como R8 na auditoria de 24/07 — continua não feito.)
2. **[P1] Resolver o conflito de rules:** em `git-workflow.mdc`, condicionar commit/push do chat a "task NÃO cancelada em andamento"; em `multiagent-orchestrator.mdc`, definir o protocolo pós-cancel (retomar task ou registrar decisão de inline com justificativa) — hoje o par de rules institucionaliza o P0-2.
3. **[P1] Health/MCP:** fazer `orchestrator mcp serve` comparar sua versão carregada com `.orchestrator/VERSION` do disco a cada tool call e anexar aviso `STALE (reload necessário)` na resposta de health/run — elimina a classe "health reporta 0.4.19".
4. **[P1] Adicionar `D:\` ou `D:\GuardLine.BR` aos `discover_roots`** (default em `Orchestrator.Common.ps1:971/991`) ou persistir raiz custom no registry na instalação do GuardLine.
5. **[P2] Commitar `bin/orchestrator.js`** (diff pós-release 0.4.20) — sessão interativa.

**Estruturais (semanas):**
6. **[P1] Decidir a frota:** para os 6 projetos sem DB, ou onboarding ativo (configurar MCP no Cursor de cada workspace + 1 task piloto por projeto) ou desregistrar do propagate para reduzir superfície. Critério: 1 task real completada por projeto em 2 semanas.
7. **[P1] Medir eficácia dos fixes 0.4.15/0.4.16/0.4.19 em produção:** rodar 3 tasks reais pós-0.4.20 (1 bootstrap, 1 printbee, 1 GuardLine) até desfecho natural SEM cancel manual; verificar: nenhuma órfã RECEIVED, QUEUED dequeue automático, VALIDATING sem arrasto 740, learnings gravados. Hoje não existe nenhuma task completada pós-0.4.15 que comprove os fixes.
8. **[P2] Learning em cancel:** gravar learning mínimo (estado, duração, último agente, motivo se fornecido) sempre que `cancel()` for aceito — cobre o gap de 17% de cobertura de memória.
9. **[P2] Backup do registry:** incluir `projects.json` do `%LOCALAPPDATA%` no backup pre-update (hoje só o workspace é backupado), mitigando o cenário do P1-4.
10. **[P2] Reexecutar esta auditoria com acesso pleno** (sessão interativa): contagens vivas dos DBs de printbee/GuardLine/adzora, últimos 20 tasks por projeto e verificação do health MCP real por workspace.

## 6. Critérios de aceitação da auditoria

- **AC-001 (entregável no workspace):** este relatório em `docs/audits/2026-07-25-multi-project-orchestrator-usage-audit.md`. ✅
- **AC-002 (achados com evidência verificável):** 11 achados (2×P0, 4×P1, 4×P2 + limitação de método), cada um com path/arquivo:linha ou evento de DB citado; todos os artefatos citados residem no workspace. ✅
- **AC-003 (recomendações priorizadas):** 10 recomendações, 5 quick wins + 5 estruturais, com critérios de verificação. ✅
- **Matriz com os 10 projetos:** seção 2. ✅
- **Restrições respeitadas:** execução 100% inline (sem spawn_agent/collab/Task); nenhum commit/push; nenhuma alteração de código. ✅

## 7. Verificação da 2ª iteração (VAL-001..004 / TEST-FAIL)

A iteração 2 recebeu rejeições VAL-001..003 ("critério não atendido") e VAL-004/TEST-FAIL (`npm test` exit=1). Verificação:

### 7.1 VAL-001..003 — falso-positivo pelo mecanismo `changed_files_since` vazio

O relatório (AC-001), os 11 achados (AC-002) e as 10 recomendações (AC-003) foram gravados neste arquivo **na iteração 1**; o snapshot da iteração 2 não viu arquivos novos e o gate rejeitou. É exatamente o mecanismo já documentado na task `5e18b4339f22` (STATUS.md, "2ª iteração — correção VAL-001": "deliverable pré-existia ao snapshot da iteração, `changed_files_since` vazio") e nos achados P-5/P-8 de `docs/audits/2026-07-24-conversation-orchestrator-usage-audit.md`. Esta seção é a mudança material da iteração 2.

Agravante estrutural: **nenhum validator de mérito chegou a rodar nesta iteração** (ver 7.2) — as rejeições vieram do gate determinístico, sem avaliação semântica do conteúdo.

### 7.2 Evidência nova — fail-fast 0.4.15 comprovado em produção; cadeia de validators degradada

Artefatos desta própria task (`.orchestrator/runtime/results/9d80c6ee4730/`):

- `validator-codex.txt` (297.272 bytes) termina com a linha literal: `[INFRA-FAIL-FAST] windows sandbox: runner failed (detected 3x, killed after 3 occurrences)` — **primeira prova em produção** de que o fail-fast de 0.4.15 (`agents/process.py`, `agent_infra_fail_fast_count=3`) mata o Codex travado em vez de esperar o timeout de 1800s. Reduz o P1-1 de "eficácia não medida" para "kill funciona; Codex segue inviável como validator no Windows mesmo com override de sandbox".
- `validator-opencode.txt` (173 bytes): fallback rotacionado falhou com `Error: {"name": "UnknownError", "data": {"message": "Unexpected server error. Check server logs for details.", "ref": "err_90f6bcb7"}}`. Com codex morto e opencode em erro de servidor, a task ficou sem validator de mérito — os dois fallbacks do perfil (`validator: [codex, opencode]`) esgotados.

### 7.3 VAL-004/TEST-FAIL (`npm test` exit=1) — não reproduzível nesta sessão; checagens estáticas PASS

`npm test` (e qualquer exec: git, python, sqlite3) segue bloqueado por approval gate na sessão autônoma — mesma limitação registrada na nota de método. Checagens estáticas realizadas nesta iteração:

- `VERSION` raiz == `package/template/.orchestrator/VERSION` == `0.4.20` → sem mismatch de `Test-Install` (classe do fix 0.4.13);
- `tests/Run-AllTests.ps1:9` limpa `ORCHESTRATOR_CHILD_AGENT` → bug-017 (suite abortando sob VALIDATING) coberto;
- `bin/orchestrator.js` (modificado, P2-4) **não tem entrada** em `package/checksums.json` → não é quebra de checksum;
- nenhuma das 28 suítes `tests/Test-*.ps1` depende de estado git.

Causa mais provável: falha de infra do ambiente TESTING sandboxed (suites spawnam `powershell.exe` filho e sondam CLIs), mesma classe dos falsos-positivos de `npm test` em VALIDATING já verificados em 24/07 (STATUS.md, verificação 0.4.14: "VAL-004/TEST-FAIL npm test = falso-positivo VALIDATING"). **Pendente interativo:** rodar `npm test` fora do sandbox e anexar a saída; se falhar de verdade, tratar como bug novo.

### 7.4 Re-verificação das evidências da iteração 1

- DB local re-contado nesta iteração (`tr -d '\000' | grep`): `to CANCELLED`=19, `to INCOMPLETE`=8, `to FAILED`=5, `to QUEUED`=0 — idêntico às seções 2/3.
- `propagate-update.json` presente; 4 learnings em `.orchestrator/memory/learnings/`.
- Acesso externo re-testado e negado de novo (registry `%LOCALAPPDATA%`, `D:\StarFusion\printbee`) — nota de método continua válida.
