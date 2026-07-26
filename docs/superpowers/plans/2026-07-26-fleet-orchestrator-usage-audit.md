# Auditoria de Uso da Frota (0.4.25) + Onboarding de Agentes — Plano de Implementação

> **For agentic workers:** Executar INLINE nesta sessão (ORCHESTRATOR_CHILD_AGENT=1 — PROIBIDO subagentes). Usar superpowers:executing-plans. Passos usam checkbox (`- [ ]`).

**Goal:** Produzir o relatório `docs/audits/2026-07-26-fleet-orchestrator-usage-and-agent-onboarding.md` diagnosticando por que a frota não usa o orquestrador corretamente, com evidência verificável e um bloco canônico vendor-neutro (≤ 60 linhas, PT) pronto para distribuição em CLAUDE.md / AGENTS.md / GEMINI.md.

**Architecture:** Auditoria read-only. Dados vivos do prompt (registry, contagens SQLite, bytes de adapter, incidente 2026-07-26) são VERDADE — não recontar. Trabalho novo = leitura de arquivos reais (template adapters vs. rules do Cursor), verificação de encoding, contagem de backups, análise causal, redação do relatório.

**Tech Stack:** Read/Grep/Glob + PowerShell somente-leitura (`Format-Hex`, `Get-ChildItem`, `Measure-Object`). Sem commit, sem push, sem npm test/pytest, sem alterar código de runtime.

## Global Constraints

- ORCHESTRATOR_CHILD_AGENT=1: tudo inline, zero subagentes, zero Task/Agent tool.
- Dataset do prompt é verdade canônica; citar como "dataset 2026-07-26" (AC-002 permite "número do dataset acima").
- Criar SOMENTE arquivo novo `docs/audits/2026-07-26-fleet-orchestrator-usage-and-agent-onboarding.md` (AC-001). NÃO editar auditorias anteriores (inclui a untracked `2026-07-25-multi-project-orchestrator-usage-audit.md`).
- Bloco canônico: português, ≤ 60 linhas, vendor-neutro, texto integral copiável (AC-003).
- Restrições de execução: proibido `npm test`, `pytest`, commit, push, edição de runtime. Leitura + relatório apenas.
- Pós-escrita (regras OpenWolf): atualizar `.wolf/anatomy.md`, `.wolf/memory.md`, `.wolf/STATUS.md`.
- Armadilha conhecida (task 9d80c6ee4730, INCOMPLETE por VAL-001/VAL-002): o validator checa presença do entregável + evidências NO workspace. O relatório deve ser arquivo NOVO criado nesta task (nunca reaproveitar arquivo pré-existente) e cada achado deve citar caminho/linha ou número do dataset.

---

### Task 1: Coletar evidência — superfície de instruções por vendor

**Files:**
- Read: `package/template/adapters/claude/CLAUDE.md`
- Read: `package/template/adapters/gemini/GEMINI.md` e `package/template/adapters/gemini/GEMINI.section.md`
- Read: `package/template/adapters/codex/AGENTS.section.md` e `package/template/adapters/codex/AGENTS.codex.section.md`
- Read: `package/template/adapters/kimi/KIMI.md`, `package/template/adapters/opencode/AGENTS.section.md`
- Read: `package/template/adapters/cursor/.cursor/rules/multiagent-orchestrator.mdc` (5077 bytes — instruções ricas)
- Read: `package/template/adapters/cursor/.cursor/rules/orchestrator.mdc`, `runtime.mdc`, `call-agent.mdc` (inventário do que SÓ o Cursor recebe)
- Read: `CLAUDE.md` (raiz deste repo, 998 bytes — cópia viva do adapter mínimo)

**Interfaces:**
- Produces: tabela comparativa "instrução × vendor" (comando run presente? task create/status? MCP mencionado? anti-recursão? aviso de backups?) com contagem de linhas por arquivo — insumo dos Achados A1 do relatório (Task 5).

- [ ] **Step 1:** Ler cada arquivo listado acima na íntegra (todos < 20 KB).
- [ ] **Step 2:** Montar tabela: para cada arquivo → bytes, linhas, e presença (sim/não + linha) de: `orchestrator run`, `task create`, `task status`, menção a MCP `orchestrator-ia`, `ORCHESTRATOR_CHILD_AGENT`, menção a `backups/`. Citar `arquivo:linha` para cada "sim".
- [ ] **Step 3:** Confirmar a hipótese central: instruções operacionais completas existem APENAS em `.cursor/rules/multiagent-orchestrator.mdc` (só Cursor lê); CLAUDE.md/GEMINI.md/AGENTS.section distribuídos não ensinam task create/status/list/cancel/logs nem MCP. Registrar contra-exemplos se existirem.

### Task 2: Verificar encoding do CLAUDE.md distribuído

**Files:**
- Read: `package/template/adapters/claude/CLAUDE.md` (já lido na Task 1 — inspecionar mojibake tipo "documentaAAo", "a†'")
- Inspect (PowerShell read-only): `D:\StarFusion\printbee\CLAUDE.md` e `D:\StarFusion\adzora\CLAUDE.md`

**Interfaces:**
- Produces: veredito de encoding com evidência hex — insumo do Achado A2.

- [ ] **Step 1:** No conteúdo lido, procurar sequências mojibake (`Ã`, `â†`, `documentaÃ§Ã£o` ou variantes). Anotar linha exata.
- [ ] **Step 2:** Capturar bytes crus do primeiro trecho suspeito:

```powershell
Format-Hex -Path "D:\StarFusion\printbee\CLAUDE.md" | Select-Object -First 40
Format-Hex -Path "D:\StarFusion\bootstrap-agents\package\template\adapters\claude\CLAUDE.md" | Select-Object -First 40
```

- [ ] **Step 3:** Classificar: (a) UTF-8 correto lido como CP1252 na distribuição (double-encode — padrão `c3 a7` virando `c3 83 c2 a7`), (b) CP1252 puro (`e7 e3 f5`, como no achado de 2026-07-23 do cerebrum), ou (c) sem problema. Registrar offsets hex como evidência. Se (c), o Achado A2 do relatório declara "hipótese de encoding refutada" com a mesma evidência.

### Task 3: Medir ruído de descoberta (backups/)

**Files:**
- Inspect (PowerShell read-only): `.orchestrator/backups/` dos 10 projetos do registry

**Interfaces:**
- Produces: contagem de pastas de backup por projeto + mitigação proposta — insumo do Achado A3.

- [ ] **Step 1:** Contar pastas de backup por projeto:

```powershell
foreach ($p in "bootstrap-agents","printbee","adzora","corehub","gangsheeter","rivero","starfusion","ukomerce","vavi") {
  $d = "D:\StarFusion\$p\.orchestrator\backups"
  if (Test-Path $d) { "{0}: {1}" -f $p, (Get-ChildItem $d -Directory | Measure-Object).Count } else { "{0}: sem backups/" -f $p }
}
if (Test-Path "D:\GuardLine.BR\.orchestrator\backups") { "GuardLine.BR: " + (Get-ChildItem "D:\GuardLine.BR\.orchestrator\backups" -Directory | Measure-Object).Count } else { "GuardLine.BR: caminho a confirmar no registry projects.json" }
```

(Se o caminho de GuardLine.BR divergir, ler `C:\Users\henrique\AppData\Local\StarFusion\orchestrator\projects.json` para o path real.)

- [ ] **Step 2:** Checar se `backups/` está em `.gitignore`/ignore de busca: Grep por `backups` em `.gitignore`, `.orchestrator/.gitignore`, `package/template/**/.gitignore`.
- [ ] **Step 3:** Redigir mitigação concreta (mínimo 3 opções, com trade-off em 1 linha cada): (1) mover backups para `%LOCALAPPDATA%\StarFusion\orchestrator\backups\<projeto>\` fora da árvore do repo; (2) retenção máxima N=5 snapshots com poda no runtime; (3) instrução explícita "NÃO vasculhar backups/" no bloco canônico + entrada em `.gitignore`/`.rgignore`. Recomendar combinação e marcar (1)-(2) como mudança de runtime = backlog (fora do escopo desta auditoria).

### Task 4: Análise causal — cancelamento 68,6% × desconhecimento operacional

**Files:**
- Read: `docs/audits/2026-07-24-conversation-orchestrator-usage-audit.md` (padrão comprovado: cancel em EXECUTING/VALIDATING + commit inline 2min/37s/11s depois; bug-022)
- Read: `docs/audits/2026-07-25-multi-project-orchestrator-usage-audit.md` (somente leitura — contexto da frota)
- Dataset 2026-07-26 (prompt): 86 tasks, 59 CANCELLED (68,6%), 8 COMPLETED (9,3%); incidente printbee 1m38s/22.100 tokens de descoberta.

**Interfaces:**
- Produces: cadeia causal com grau de confiança — insumo do Achado A4.

- [ ] **Step 1:** Extrair das auditorias anteriores os casos documentados de cancel→inline (task ids, timestamps) e citar `arquivo:linha`.
- [ ] **Step 2:** Montar a cadeia causal: agente não sabe operar (sem `task status`/`logs` nas instruções que ele lê) → não acompanha → operador percebe "travado" → cancela → refaz inline → CANCELLED domina. Confrontar com causas alternativas documentadas (validator codex erro 740 arrastando VALIDATING; bug-022 cancel não mata loop) e classificar a contribuição de cada causa como direta/indireta, com evidência por item.
- [ ] **Step 3:** Ser explícito sobre limite: dataset dá correlação + mecanismo documentado em casos individuais; não há experimento controlado. Redigir conclusão como "causalidade provável, mecanismo demonstrado em N casos", não como certeza.

### Task 5: Redigir o relatório (entregável AC-001)

**Files:**
- Create: `docs/audits/2026-07-26-fleet-orchestrator-usage-and-agent-onboarding.md`

**Interfaces:**
- Consumes: tabelas e vereditos das Tasks 1–4.
- Produces: relatório final com seções fixas abaixo.

- [ ] **Step 1:** Escrever o relatório com esta estrutura obrigatória:
  1. Sumário executivo (≤ 15 linhas: 4 achados + recomendação única).
  2. Metodologia e fontes (dataset 2026-07-26 como verdade; arquivos lidos; comandos executados).
  3. Achado A1 — assimetria de instruções por vendor (tabela da Task 1, com `arquivo:linha`).
  4. Achado A2 — encoding do CLAUDE.md distribuído (hex da Task 2; confirmado OU refutado).
  5. Achado A3 — ruído de descoberta backups/ (contagens da Task 3 + mitigações).
  6. Achado A4 — cadeia causal cancelamento × onboarding (Task 4).
  7. Incidente motivador 2026-07-26 anotado passo a passo (sequência do prompt) mapeando cada passo perdido → linha do bloco canônico que o teria evitado.
  8. Recomendações priorizadas (P0/P1/P2), separando "distribuir bloco canônico" (P0, sem código) de mudanças de runtime (backlog).
  9. **Seção final: texto integral do bloco canônico** (ver Step 2) dentro de um único fence markdown, precedido de "Copiar o bloco abaixo para CLAUDE.md, AGENTS.md e GEMINI.md de todos os projetos:".
- [ ] **Step 2:** Bloco canônico — partir do rascunho abaixo, CORRIGINDO os nomes de comando contra a superfície real do CLI antes de finalizar (ler `package/bin/` ou `package/src/cli*` ou executar `orchestrator --help` e `orchestrator task --help`, read-only). Se algum subcomando do rascunho não existir (ex.: `task logs`), substituir pelo equivalente real ou remover. Manter ≤ 60 linhas.

```markdown
## Orquestrador StarFusion — guia rápido para agentes (v0.4.25)

Este projeto usa o runtime persistente do Orchestrator. NÃO reimplemente
orquestração nem vasculhe o repo para "descobrir" como invocá-lo: use isto.
Config canônica: `.orchestrator/config/` (models.json, policies.json).

### Antes de tudo
1. Se a variável `ORCHESTRATOR_CHILD_AGENT=1` estiver no ambiente, você JÁ É
   um agente filho do orquestrador: PROIBIDO chamar `orchestrator` de novo,
   criar subagentes ou delegar. Execute o trabalho inline e retorne.
2. Verifique staleness: `orchestrator version` e compare com
   `.orchestrator/VERSION`. Se divergirem, avise o operador; não atualize.

### Interface: MCP ou CLI
- MCP `orchestrator-ia` (configurado em `.cursor/mcp.json`): preferido quando
  seu ambiente expõe as tools MCP (task_create, task_status, ...).
- CLI `orchestrator` (no PATH): fallback universal, mesmos comandos abaixo.

### Comandos essenciais (CLI)
- Atividade completa (síncrona):  `orchestrator run --prompt "<atividade>"`
- Criar task assíncrona:          `orchestrator task create --prompt "<atividade>"`
- Acompanhar uma task:            `orchestrator task status <task_id>`
- Listar tasks do projeto:        `orchestrator task list`
- Ver logs/artefatos:             `orchestrator task logs <task_id>`
- Cancelar (ÚLTIMO recurso):      `orchestrator task cancel <task_id>`

### Acompanhe até o fim — não cancele por impaciência
- Fluxo normal: RECEIVED → PLANNING → EXECUTING → VALIDATING → COMPLETED.
- EXECUTING/VALIDATING = trabalhando. Consulte `task status` periodicamente.
- Cancelar e refazer inline zera o diff da task, fabrica INCOMPLETE falso e
  corrompe as métricas da frota. Se não há evento novo por mais de 30 min,
  reporte o task_id ao operador ANTES de qualquer cancel.

### O que NÃO fazer
- NÃO vasculhar `.orchestrator/backups/` (dezenas de snapshots; só ruído).
  Limite buscas a `.orchestrator/config/` e docs do projeto.
- NÃO editar `.orchestrator/` manualmente; o runtime é dono do diretório.
- NÃO rodar orquestrador dentro de orquestrador (regra 1).
```

- [ ] **Step 3:** Validar AC-003 mecanicamente: contar linhas do bloco final (≤ 60) com `(Get-Content <arquivo temporário do bloco> | Measure-Object -Line).Lines` ou contagem manual no fence.

### Task 6: Autoverificação + OpenWolf

**Files:**
- Modify: `.wolf/anatomy.md` (registrar relatório + plano), `.wolf/memory.md` (append), `.wolf/STATUS.md` (quest ✅)

**Interfaces:**
- Consumes: relatório da Task 5.

- [ ] **Step 1:** Checklist AC: AC-001 arquivo novo existe no caminho exato; AC-002 todo achado tem `arquivo:linha`, offset hex, contagem PowerShell ou referência "dataset 2026-07-26"; AC-003 bloco integral ≤ 60 linhas em português na seção final.
- [ ] **Step 2:** Reler o relatório procurando afirmação sem evidência; corrigir inline.
- [ ] **Step 3:** Atualizar `.wolf/anatomy.md`, `.wolf/memory.md`, `.wolf/STATUS.md`. Sem commit.

---

## Ajustes propostos ao plano JSON do orquestrador

Os `acceptance_criteria` genéricos do plano atual conflitam com as restrições do prompt:

1. `AC-002 tests_pass` — proibido rodar `npm test`/`pytest` nesta task. Substituir por check estático: presença de evidências (`grep` por citações `:linha`/hex no relatório) ou marcar tester `runtime.run_tests` como skip.
2. `AC-003 docs_example (README.md)` — o entregável é `docs/audits/2026-07-26-fleet-orchestrator-usage-and-agent-onboarding.md`; apontar o check para esse path (o "exemplo executável" = bloco canônico copiável + comandos PowerShell reproduzíveis).
3. `AC-001 workspace_changes` — satisfeito pelo arquivo novo do relatório + este plano + updates `.wolf/`. Atenção ao falso-negativo conhecido de `changed_files_since` (task 5e18b4339f22, seção 8): o relatório é criado DEPOIS do snapshot da iteração, então o diff será não-vazio.
4. Passo `documentation/update_docs`: escopo = nenhum doc de runtime a atualizar (auditoria read-only); apenas `.wolf/` já coberto na Task 6.
