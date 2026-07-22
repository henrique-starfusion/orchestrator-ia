# Project Audit — Orquestrador IA Multiagente (ex bootstrap-agents) 2026-07-21

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produzir `docs/audits/2026-07-21-project-analysis.md` com achados categorizados (crítico/alto/médio/baixo), evidências arquivo:linha, impacto e recomendações. Relatório READ-ONLY — nenhuma feature ou fix implementado.

**Architecture:** Executor (Claude/esta sessão) lê o codebase e produz o relatório. Validador (agente diferente, Codex) lê o relatório e confirma achados antes de encerrar. Suite de testes executada uma vez no início e resultado anexado ao relatório como evidência.

**Tech Stack:** PowerShell 5.1 (installer scripts), Python 3 / pytest (runtime), Node.js (CLI wrapper), TypeScript (opencode plugin). Ferramentas: `npm test`, `npm run test:runtime`.

## Global Constraints

- NENHUM arquivo editado exceto o novo `docs/audits/2026-07-21-project-analysis.md`.
- Nenhuma feature nova. Nenhum fix. Apenas leitura + documentação.
- Validador deve ser agente diferente do executor (requirement de `policies.json: require_independent_validation=true`).
- Evidências devem usar formato `arquivo:linha` exato.
- Aceitação mínima de score 0.9 do validador conforme `policies.json`.

---

## Acceptance Criteria corrigidos

| ID | Critério | Verificável | Obrigatório |
|----|----------|-------------|-------------|
| AC-001 | `docs/audits/2026-07-21-project-analysis.md` existe com seções crítico/alto/médio/baixo | sim | sim |
| AC-002 | Cada achado crítico/alto tem evidência `arquivo:linha`, root cause, impacto, recomendação | sim | sim |
| AC-003 | Saída completa do `npm test` (exit code + pass/fail por suite) está anexada no relatório | sim | sim |
| AC-004 | Saída completa do `npm run test:runtime` está anexada no relatório | sim | sim |
| AC-005 | WriteLock deadlock documentado com root cause em `execution/locks.py` e cenário de falha | sim | sim |
| AC-006 | Bug AC-generator documentado com linha exata em `planning/analyzer.py` e keyword "sum" | sim | sim |
| AC-007 | Mínimo 3 gaps (CI/CLI/security/docs) com evidência de arquivo | sim | sim |
| AC-008 | Validador independente (agente diferente do executor) confirma achados críticos/altos | sim | sim |

---

## Diagnostic do plano anterior

**Por que o plano fornecido estava errado:**
O `CriteriaBuilder.build()` em `runtime/src/orchestrator_runtime/planning/analyzer.py:104` contém:
```python
if "soma" in lowered or "sum" in lowered:
    add("Existe função soma(a, b) retornando a soma numérica")
    add("Há teste automatizado cobrindo soma(2,3)==5")
```
Qualquer prompt com "sum" (incluindo "summary", "assumption", "resume") dispara critérios de "soma". É artefato de demo vazado para produção. O `test_rules_manager.py:13` usa exatamente `"Crie um modulo Python com funcao soma"` para validar esse comportamento — o teste protege o bug. Esse é Achado ALTO do audit.

---

## Task 1: Executar suíte de testes e capturar saída

**Files:**
- Read (capture output): `tests/Run-AllTests.ps1` (via `npm test`)
- Read (capture output): `runtime/tests/` (via `npm run test:runtime`)
- Create note: resultado vai para seção "Anexo A" do relatório final

- [ ] **Step 1: Rodar suíte PowerShell**

```powershell
npm test
```

Esperado: saída com pass/fail por suite (14 suítes conforme STATUS.md). Gravar exit code e output completo.

- [ ] **Step 2: Rodar suíte Python**

```powershell
npm run test:runtime
```

Esperado: pytest output com pass/fail por módulo. Gravar exit code e output completo.

- [ ] **Step 3: Gravar ambos os outputs como bloco de texto para anexar ao relatório**

Formato esperado para o relatório:
```
## Anexo A — Resultado das Suítes de Teste (2026-07-21)

### npm test (PowerShell)
Exit code: N
<output completo>

### npm run test:runtime (Python)
Exit code: N
<output completo>
```

---

## Task 2: Audit WriteLock / Resume Deadlock

**Files:**
- Read: `runtime/src/orchestrator_runtime/execution/locks.py` (WriteLock, L11-42)
- Read: `runtime/tests/unit/test_resume.py` (cobertura de resume)
- Read: `runtime/src/orchestrator_runtime/execution/workspace.py` (uso do lock)
- Read: `.opencode/plugin/openwolf/anatomy.ts:245-275` (lock TypeScript — referência de contraste)

- [ ] **Step 1: Ler locks.py e anotar gap**

```
runtime/src/orchestrator_runtime/execution/locks.py:17-30
```
`WriteLock.acquire()` faz spin com `time.sleep(0.2)` e lança `TimeoutError` após `timeout_s` (default 30s). Nenhuma detecção de PID stale. Se o processo holder crashar, o lock file persiste indefinidamente na próxima execução o resume falha com `TimeoutError`.

- [ ] **Step 2: Ler test_resume.py e verificar se cobre deadlock**

Verificar: o teste simula crash-with-lock-held e testa que o lock é detectado como stale?

- [ ] **Step 3: Contrastar com anatomy.ts**

`anatomy.ts:255-258`: verifica PID liveness via `process.kill(pid, 0)` e rename do lock stale. Python lock não tem equivalente.

- [ ] **Step 4: Documentar achado**

```
CRÍTICO
Arquivo: runtime/src/orchestrator_runtime/execution/locks.py:17-30
Root cause: WriteLock.acquire() sem stale detection por PID — lock file de processo
  morto bloqueia resume até TimeoutError(30s), sem possibilidade de recuperação.
Cenário: orchestrator task resume <id> após crash do runner → TimeoutError →
  task fica presa em estado EXECUTING, nunca retorna a PLANNING.
Impacto: toda feature de resume/retry fica inacessível em crash.
Recomendação: ler PID do lock file e checar se processo está vivo (os.kill(pid, 0));
  se ESRCH → deletar lock stale (como anatomy.ts:255-258 faz).
```

---

## Task 3: Audit — CriteriaBuilder gerando AC genérico de "soma"

**Files:**
- Read: `runtime/src/orchestrator_runtime/planning/analyzer.py:85-115` (CriteriaBuilder)
- Read: `runtime/tests/unit/test_rules_manager.py` (confirmar que o teste usa prompt de "soma")
- Read: `runtime/src/orchestrator_runtime/planning/strategies.py` (estratégia hardcoded)

- [ ] **Step 1: Ler CriteriaBuilder e anotar linhas exatas**

```python
# analyzer.py:104-106
if "soma" in lowered or "sum" in lowered:
    add("Existe função soma(a, b) retornando a soma numérica")
    add("Há teste automatizado cobrindo soma(2,3)==5")
```

Problema 1: keyword "sum" é substring de "summary", "assumption", "resume", "consumption" → falso positivo.
Problema 2: critérios de "soma" são literais hardcoded de demo — não descrevem a tarefa real.
Problema 3: `test_rules_manager.py:13` usa exatamente `"Crie um modulo Python com funcao soma"` → o teste valida o comportamento errado, não o bug.

- [ ] **Step 2: Verificar fallback genérico**

```python
# analyzer.py:111-114
if not criteria:
    add("Alterações solicitadas no prompt estão presentes no workspace")
    add("Testes determinísticos relevantes passam ou estão justificados")
    add("Documentação afetada foi revisada e atualizada se necessário")
```

Para tasks sem keywords (audit, análise de arquitetura, refactor), os critérios são genéricos demais para verificação determinística.

- [ ] **Step 3: Documentar achado**

```
ALTO
Arquivo: runtime/src/orchestrator_runtime/planning/analyzer.py:104-106
Root cause: CriteriaBuilder.build() usa substring hardcoded "sum" para gerar AC
  de demo ("soma(a,b)") que não tem relação com a task real. "sum" está presente
  em palavras como "summary", "resume", "assumption".
Impacto: o plano entregue ao executor contém critérios de validação errados →
  validador avalia critérios irrelevantes → score alto por critério errado →
  tarefa marcada COMPLETED com work product incorreto.
Evidência: test_rules_manager.py:13 confirma o comportamento com prompt de "soma" —
  o teste protege o bug (não é uma cobertura correta).
Recomendação: substituir CriteriaBuilder por extração semântica da tarefa real
  (ex: se task_type == "audit_report", gerar AC específico de relatório com seções,
  evidências e achados verificáveis). Remover exemplos de demo do código de produção.
```

---

## Task 4: Audit — Gaps de CI / DX CLI / Segurança / Docs

**Files:**
- Read: `bin/orchestrator.js:82-84` (set known commands)
- Read: `bin/orchestrator.js:19-44` (printHelp)
- Read: `package.json:46-49` (scripts)
- Glob: `.github/**` (esperado: vazio)
- Read: `docs/security.md` (cobertura de segurança)
- Read: `.gitignore` (secrets em ignore?)
- Read: `tests/Run-AllTests.ps1` (link para runtime tests?)

- [ ] **Step 1: Verificar `orchestrator agents`**

```javascript
// bin/orchestrator.js:82-84
const known = new Set([
  'init', 'i', 'install', 'verify', 'update', 'upgrade', 'repair', 'uninstall',
  'status', 'analyze', 'skills', 'global-tools', 'route', 'dispatch', 'legacy',
  'run', 'task', 'tools', 'mcp', 'cursor',
]);
```

`agents` não está no set. Executar `orchestrator agents` → passa para Install-Orchestrator.ps1 como subcomando desconhecido → erro opaco, sem sugestão de `orchestrator status`.

Documentar achado MÉDIO.

- [ ] **Step 2: Verificar CI**

```bash
ls .github/
# esperado: diretório inexistente
```

Confirmar ausência. 27 suítes PS1 + runtime Python sem CI pipeline. Push para main/develop não dispara testes.

Documentar achado MÉDIO.

- [ ] **Step 3: Verificar cobertura de runtime Python em npm test**

`package.json:46`: `"test": "powershell ... tests/Run-AllTests.ps1"` — não inclui `test:runtime`. Runtime Python tem 17 arquivos de teste mas não é executado pelo `npm test` padrão. Qualquer regressão Python passa despercebida pelo CI manual.

Documentar achado MÉDIO.

- [ ] **Step 4: Verificar segurança**

Ler `docs/security.md` e `.gitignore`. Verificar:
- API keys / tokens no gitignore?
- Secrets scanning (ex: trufflehog, gitleaks) ausente?
- `orchestrator dispatch` recebe `--prompt` como argumento de linha de comando — possível leak de prompt em `ps aux` / logs do SO?

- [ ] **Step 5: Verificar freshness de docs**

`anatomy.md` stale (aviso de startup: "git HEAD moved since last scan").
`docs/runtime-architecture.md` — verifica se descreve o runtime Python como beta/WIP ou apresenta como feature completa.

Documentar achados BAIXO.

---

## Task 5: Audit — Arquitetura Runtime / MCP / Installer

**Files:**
- Read: `runtime/src/orchestrator_runtime/execution/runner.py` (state machine runner)
- Read: `runtime/src/orchestrator_runtime/tasks/state_machine.py` (estados)
- Read: `bin/orchestrator.js:52-57` (isRuntimeCommand, handoff para Python)
- Read: `docs/runtime-architecture.md` (documentação do runtime)
- Read: `scripts/Configure-Mcps.ps1` (MCP serve impl)
- Read: `.orchestrator/orchestration/workflows/` (vazio — gap documentado)
- Read: `bug-003` em `.wolf/buglog.json:29-39` (deep-merge pendente)

- [ ] **Step 1: Verificar handoff Node→Python**

```javascript
// bin/orchestrator.js:52-57
function isRuntimeCommand(command, argv) {
  if (command === 'run') return true;
  if (command === 'task') return true;
  return false;
}
```

Verificar: `runtimeSrc = path.join(packageRoot, 'runtime', 'src')` — o Node checa se Python está disponível antes de tentar invocar? Se Python não estiver no PATH, que erro o usuário vê?

- [ ] **Step 2: Verificar MCP serve**

Ler `Configure-Mcps.ps1` e verificar se `orchestrator mcp serve --transport stdio|http` tem implementação real ou é stub.

- [ ] **Step 3: Verificar estado de `orchestration/workflows/`**

```
.orchestrator/orchestration/workflows/  → apenas .gitkeep
```

STATUS.md declara "Engine daemon autônomo fica pro roadmap" mas o diretório está no template distribuído. Usuários instalando o pacote recebem estrutura de diretórios sem conteúdo.

- [ ] **Step 4: Verificar bug-003 scope**

`buglog.json:bug-003`: deep-merge de mode=merge não implementado. Qualquer projeto novo que rodar `orchestrator update` perde chaves novas de `models.json` (ex: `model_flag` de opencode/gemini). Verificar quantos projetos potencialmente afetados.

- [ ] **Step 5: Documentar achados de arquitetura**

Classificar:
- Handoff Python sem verificação de dependência → MÉDIO
- MCP serve status real vs documentado → MÉDIO/BAIXO
- Workflows vazio distribuído → BAIXO
- bug-003 deep-merge → ALTO (já logado, confirmar scope)

---

## Task 6: Síntese — Escrever docs/audits/2026-07-21-project-analysis.md

**Files:**
- Create: `docs/audits/2026-07-21-project-analysis.md`
- Read (inputs): saídas das Tasks 1-5

- [ ] **Step 1: Estruturar relatório com template**

```markdown
# Auditoria — bootstrap-agents (2026-07-21)

> Auditoria read-only. Nenhum arquivo editado exceto este.
> Branch auditada: feature/call-agent-profiles
> Executor: Claude (sonnet-4-6)
> Validador: Codex (ver Seção 6)

## Sumário executivo

<2-3 parágrafos: estado geral, achados críticos, recomendações imediatas>

## 1. Achados Críticos

### C-001 — WriteLock sem stale detection
...

## 2. Achados Altos

### A-001 — CriteriaBuilder gera AC de "soma" por keyword hardcoded
...
### A-002 — bug-003: deep-merge mode=merge pendente
...

## 3. Achados Médios

### M-001 — CI inexistente
### M-002 — `orchestrator agents` comando inválido (DX)
### M-003 — Runtime Python excluído do npm test padrão
### M-004 — Handoff Node→Python sem verificação de dependência

## 4. Achados Baixos

### B-001 — anatomy.md stale
### B-002 — `orchestration/workflows/` vazio distribuído
### B-003 — Prompt via --arg exposto em process list

## 5. Resultado das Suítes de Teste

### 5.1 npm test (PowerShell)
<output da Task 1>

### 5.2 npm run test:runtime (Python)
<output da Task 1>

## 6. Validação Independente (Codex)

> Agente: codex | task_class: complex_analysis
> Prompt enviado ao validador: <ver abaixo>
> Status: <completed|failed>
> Confirmações: <lista de achados confirmados>
> Divergências: <se houver>

## 7. Recomendações priorizadas

| Prioridade | Achado | Esforço | Risco de não fazer |
|---|---|---|---|
| 1 | C-001 WriteLock stale | 1h | resume impossível após qualquer crash |
| 2 | A-001 CriteriaBuilder | 2h | AC incorretos → validação falsa |
| 3 | A-002 bug-003 deep-merge | 3h | projetos novos perdem model routing |
| 4 | M-001 CI pipeline | 4h | regressões não detectadas |
| 5 | M-002 agents DX | 30min | UX ruim no CLI |
```

- [ ] **Step 2: Preencher cada achado com evidências coletadas nas Tasks 2-5**

Cada achado: título, severidade, arquivo:linha, root cause, impacto concreto, recomendação com esforço estimado.

- [ ] **Step 3: Inserir output completo dos testes no Anexo (Seção 5)**

- [ ] **Step 4: Salvar arquivo**

---

## Task 7: Validação Independente por Codex

**Files:**
- Read: `docs/audits/2026-07-21-project-analysis.md` (o relatório gerado)
- Execute: `orchestrator dispatch --task-class complex_analysis --client codex`
- Write: resultado de validação na Seção 6 do relatório

- [ ] **Step 1: Verificar pre-conditions**

```powershell
$env:ORCHESTRATOR_CHILD_AGENT
# deve estar vazio (nao somos child agent)
```

- [ ] **Step 2: Montar prompt de validação (codex não é fire-and-forget)**

```
Leia o relatório de auditoria em docs/audits/2026-07-21-project-analysis.md.
Para cada achado crítico e alto, responda:
1. O achado é correto com base no código fonte? (sim/não + evidência arquivo:linha)
2. A root cause está correta?
3. A recomendação é adequada?
Formato de saída: JSON com lista de achados, campo "confirmed": true/false e "notes".
```

- [ ] **Step 3: Dispatchar para codex e monitorar**

```powershell
orchestrator dispatch `
  --task-class complex_analysis `
  --client codex `
  --prompt "<prompt acima>"
```

Acompanhar output ao vivo (obrigatório — não fire-and-forget per SKILL call-agent passo 5).
Verificar `runtime/results/*-complex_analysis-status.json` → `"status": "completed"`.

- [ ] **Step 4: Inserir resultado de validação na Seção 6 do relatório**

Confirmar: validador confirmou achados C-001 e A-001? Se divergência → adicionar nota e não alterar classificação sem evidência adicional.

- [ ] **Step 5: Verificar AC-008**

Score de confirmação ≥ 0.9 (≥ 90% dos achados críticos/altos confirmados pelo validador).

---

## Self-Review

### Spec coverage

| Foco solicitado | Tarefa cobrindo |
|---|---|
| WriteLock/resume deadlock | Task 2 |
| AC genérico "soma" | Task 3 |
| Gaps CI/CLI/docs/security/DX | Task 4 |
| Arquitetura runtime/MCP/installer | Task 5 |
| Resultado de testes | Task 1 |
| Validação por agente diferente | Task 7 |
| Relatório `docs/audits/2026-07-21-project-analysis.md` | Task 6 |

Todos os focos cobertos. Nenhum placeholder.

### AC check

- AC-001: Task 6 cria o arquivo com seções. ✓
- AC-002: Tasks 2-5 coletam evidências arquivo:linha para cada achado. ✓
- AC-003: Task 1 captura `npm test` output → Task 6 Seção 5. ✓
- AC-004: Task 1 captura `npm run test:runtime` → Task 6 Seção 5. ✓
- AC-005: Task 2 documenta WriteLock em locks.py com cenário. ✓
- AC-006: Task 3 documenta analyzer.py:104 com keyword "sum". ✓
- AC-007: Task 4 documenta CI, DX CLI, security. ≥3 gaps. ✓
- AC-008: Task 7 despacha Codex como validador independente. ✓
