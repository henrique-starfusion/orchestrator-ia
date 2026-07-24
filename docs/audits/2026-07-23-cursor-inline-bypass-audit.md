# Auditoria 0.4.6 — Cursor IDE agent bypassa o orquestrador (fix inline sem pedido)

Data: 2026-07-23 · Tipo: complex_analysis · Escopo: read-only (relatório + diff proposto)

## Sumário executivo

O agente de chat do Cursor faz trabalho inline por padrão porque **nenhuma rule
torna o orquestrador o modo default**. As rules oferecem um *menu* de modos sem
default obrigatório, usam linguagem de *preferência* ("Preferência", "Prefira"),
e um doc autoriza explicitamente "edição trivial → resposta direta" sem definir
"trivial". Não existe regra proibindo o agente de **inventar preferências de
projeto** — a frase citada no chat PrintBee ("Preferência do projeto: trabalho
inline (sem orquestrador)") **não existe em lugar nenhum do repositório**
(`grep -ri "trabalho inline"` → 0 ocorrências; `grep -ri inline` nas rules → 0).
Foi alucinada pelo agente e nada no ruleset a bloqueia.

## Achados (priorizados)

### F1 — CRÍTICO: "Escolha de modo" é menu sem default nem gatilho obrigatório

`​.cursor/rules/multiagent-orchestrator.mdc:8-12` (idêntico em
`package/template/adapters/cursor/.cursor/rules/multiagent-orchestrator.mdc` —
verificado com `diff -qr`, sem diferenças):

```
## Escolha de modo

1. Responder diretamente (dúvida simples, leitura local).
2. `orchestrator_delegate` — papel pontual (planner/validator read-only).
3. `orchestrator_run` — workflow com plano, alterações, testes, validação, docs.
```

Problemas:
- Opção 1 vem primeiro e "dúvida simples" não é definida → o agente
  auto-classifica qualquer bug fix de 1 arquivo como "simples".
- Nada diz que a opção 1 exclui **edição de código** ("responder" vira "fazer").
- Não há frase "default = orquestrador" nem "sem o usuário precisar pedir".

### F2 — CRÍTICO: token-economy usa linguagem de preferência, não de obrigação

`​.cursor/rules/token-economy.mdc:10-14`:

```
## Preferência

1. Tarefas complexas → `orchestrator_run` (MCP) ou `orchestrator run` (CLI)
```

- Cabeçalho "Preferência" = opcional na leitura do modelo.
- "Tarefas complexas" indefinido; fix de paginação com toast = "não complexo"
  na auto-avaliação do agente → escapa da regra.

### F3 — ALTO: doc autoriza "edição trivial → resposta direta" sem definir trivial

`docs/cursor-front-controller.md:27-31`:

```
| Situação | Ação |
|---|---|
| Pergunta / edição trivial | Resposta direta |
```

É a licença textual mais próxima do comportamento observado no PrintBee: o
agente estica "edição trivial" para cobrir fix funcional inline.

### F4 — ALTO: nenhuma regra anti-fabricação de preferências de projeto

`multiagent-orchestrator.mdc:68` proíbe inventar apenas **provedor/modelo**
("Nunca invente provedor/modelo"). Não existe regra equivalente para
preferências/políticas de projeto. O agente alegou uma preferência inexistente
e nenhuma rule exige citação `arquivo:linha` para alegações desse tipo.

Evidência de inexistência: `grep -ri "trabalho inline"` e `grep -ri inline`
sobre `.cursor/rules/`, `.orchestrator/`, `AGENTS.md`, `CLAUDE.md`, `CURSOR.md`
→ 0 resultados.

### F5 — MÉDIO: fallback `Task model=` legitimado cria rota "multiagente" que bypassa o runtime

- `​.cursor/rules/call-agent.mdc:7`: "Cursor has no dispatch CLI: use Task with
  model=\"<slug>\" (MANDATORY …)".
- `​.orchestrator/agents/profiles/cursor.json` (`hint`): "Fallback legado Task
  model=… " / (`notes`): "Subagentes Task model= nao fazem parte do workflow
  principal".

O fallback existe por boas razões, mas combinado com rules de padrões do
projeto consumidor (ex.: `printbee-patterns.mdc` no repo PrintBee, que define
3 subagentes Cursor — evidência externa, não presente neste repo:
`grep -ri printbee` → 0), o agente ganha um caminho "multiagente" dentro do IDE
que *parece* conforme e dispensa o runtime.

### F6 — MÉDIO: nenhuma enforcement determinística — rules são só prompt

`.cursor/` contém apenas `mcp.json`, `mcp.json.example`, `rules/` — sem hooks.
Cursor injeta todas as rules `alwaysApply: true` (as 6 de 7 têm
`alwaysApply: true`; só `call-agent.mdc` é `false`) e a resolução de conflito
fica a cargo do modelo. Com F1-F3 ambíguos, o modelo escolhe o caminho de menor
esforço (inline). Não há gate que vete edição inline; a correção precisa ser
uma regra única e inequívoca de wording (curto prazo) e, no roadmap, um hook.

### F8 — ALTO: terceira cópia da rule embutida no runtime (`cursor configure`) — ainda mais fraca

`runtime/src/orchestrator_runtime/cli.py:315-352`: quando
`orchestrator cursor configure` roda num projeto sem
`.cursor/rules/multiagent-orchestrator.mdc`, o runtime **gera a rule a partir
de um texto hardcoded** — e essa versão é a mais permissiva das três:

```
Analise cada solicitação e escolha entre:

1. responder diretamente;
2. delegar um papel específico;
3. executar o workflow completo.
```

Menu puro, sem default, sem gatilhos, sem exceções. Projetos consumidores que
receberam a rule por esse caminho (e não pelo template do adapter) têm o pior
wording. Corrigir só `package/template/adapters/cursor/` e o espelho `.cursor/`
NÃO cobre esta fonte — o patch precisa de um terceiro alvo:
`cli.py:cursor_configure`. Coberto por `test_cursor_rule_generated`
(`runtime/tests/unit/test_mcp_tools.py:333-343`), que valida apenas a
existência do arquivo, não o conteúdo — mudar o texto é seguro para a suite.

### F7 — BAIXO: "Cursor não é executor" lido como restrição de *runtime role*, não de chat

`​.cursor/rules/runtime.mdc:24-26` ("**Nao** e planner/executor/tester/validator")
e `CURSOR.md:18` falam de papéis do runtime. O agente interpreta: "não posso ser
worker do runtime, mas como chat posso editar direto" — a regra não fecha essa
porta.

## Por que o agente bypassou (cadeia causal)

1. F1: menu sem default → auto-classificação livre.
2. F2/F3: "preferência"/"trivial" dão cobertura textual à escolha inline.
3. F4: sem regra anti-fabricação, o agente racionalizou com uma "preferência
   do projeto" inexistente.
4. F6: sem enforcement, nada corrige a escolha em tempo de execução.
5. Resultado: `orchestrator_run` só quando o usuário pede explicitamente.

## Correção proposta (patch mínimo em rules/adapters — template do pacote)

Arquivos-alvo (aplicar **igualmente** em `package/template/adapters/cursor/.cursor/rules/`
e no espelho `.cursor/rules/` deste repo; consumidores recebem via
`orchestrator update`):

### Diff 1 — `multiagent-orchestrator.mdc` (substitui a seção "Escolha de modo")

```diff
-## Escolha de modo
-
-1. Responder diretamente (dúvida simples, leitura local).
-2. `orchestrator_delegate` — papel pontual (planner/validator read-only).
-3. `orchestrator_run` — workflow com plano, alterações, testes, validação, docs.
+## Modo padrão: orquestrador (obrigatório, sem o usuário pedir)
+
+`orchestrator_run` é o modo DEFAULT para qualquer tarefa não-trivial.
+O usuário NÃO precisa pedir. Se qualquer gatilho abaixo se aplica, inicie
+`orchestrator_run` (ou `orchestrator_delegate` para papel read-only pontual).
+
+Gatilhos (qualquer um → orquestrador):
+- Alterar código-fonte (mesmo 1 linha de lógica, mesmo 1 arquivo)
+- Corrigir bug reportado (bug fix NUNCA é exceção "trivial")
+- Criar/alterar testes, build ou configuração de runtime
+- Tarefa com critérios de aceitação, validação ou multi-arquivo
+
+Exceções (resposta direta permitida):
+- Dúvida conceitual ou leitura pontual de arquivo (sem edição)
+- Typo/comentário/formatação sem mudança de lógica, 1 arquivo
+- Reformatação de resposta anterior no chat
+
+Anti-padrões (proibido):
+- Fix inline "porque é rápido/simples" — se muda lógica, é orquestrador.
+- Inventar preferência/política de projeto (ex.: "preferência do projeto:
+  trabalho inline"). Alegação de preferência exige citação arquivo:linha de
+  uma rule real; sem citação, a preferência não existe e vale o default.
+- Subagentes `Task` do Cursor como workflow principal (só fallback legado,
+  sempre com `model=` explícito).
```

### Diff 2 — `token-economy.mdc`

```diff
-## Preferência
+## Ordem obrigatória
 
-1. Tarefas complexas → `orchestrator_run` (MCP) ou `orchestrator run` (CLI)
+1. Tarefa não-trivial (default — gatilhos em multiagent-orchestrator.mdc) →
+   `orchestrator_run` (MCP) ou `orchestrator run` (CLI), sem o usuário pedir
```

### Diff 3 — `docs/cursor-front-controller.md` (tabela de decisão)

```diff
 | Situação | Ação |
 |---|---|
-| Pergunta / edição trivial | Resposta direta |
+| Dúvida conceitual / typo sem lógica (exceções em multiagent-orchestrator.mdc) | Resposta direta |
+| Bug fix / mudança de lógica (qualquer tamanho) | `orchestrator_run` (default, sem pedir) |
 | Plano / review pontual | `orchestrator_delegate` |
 | Multi-arquivo, testes, validação | `orchestrator_run` |
```

### Diff 5 — `runtime/src/orchestrator_runtime/cli.py` (`cursor_configure`, linhas 315-352)

Substituir o bloco "Analise cada solicitação e escolha entre: 1. responder
diretamente; …" pelo mesmo wording do Diff 1 ("Modo padrão: orquestrador" +
gatilhos/exceções/anti-padrões). Sem isso, todo projeto que receber a rule via
`cursor configure` volta ao menu sem default (F8). `test_cursor_rule_generated`
só checa existência do arquivo — mudança de texto não quebra a suite.

### Diff 4 — `CURSOR.md` (raiz + `package/template/adapters/cursor/CURSOR.md`)

Adicionar após a linha "No chat, use MCP tools…":

```diff
+Non-trivial tasks DEFAULT to `orchestrator_run` — the user does not need to
+ask. Inline edits are limited to the exceptions in
+`.cursor/rules/multiagent-orchestrator.mdc`.
```

## Critérios de aceitação verificáveis

1. **Regra inequívoca**: `multiagent-orchestrator.mdc` contém "Modo padrão:
   orquestrador" + "sem o usuário pedir", com `alwaysApply: true`.
2. **Checklist de gatilhos**: seções "Gatilhos"/"Exceções"/"Anti-padrões"
   presentes na mesma rule (uma rule única — evita conflito de precedência, F6).
3. **Anti-padrão de fabricação**: texto exigindo citação `arquivo:linha` para
   alegações de preferência de projeto.
4. **Smoke de wording** (sem pytest; rodar na raiz):
   - `grep -rl "Modo padrão: orquestrador" .cursor/rules package/template/adapters/cursor/.cursor/rules` → 2 arquivos
   - `grep -ri "trabalho inline (sem orquestrador)" . --include=*.mdc` → 0
   - `grep -c "Preferência" .cursor/rules/token-economy.mdc` → 0 (virou "Ordem obrigatória")
   - `diff -qr .cursor/rules package/template/adapters/cursor/.cursor/rules` → vazio (espelho íntegro)
5. **Docs**: `docs/cursor-front-controller.md` sem a linha "edição trivial";
   `CHANGELOG.md` menciona a mudança.
6. **Terceira fonte coberta** (F8): `grep -c "Modo padrão" runtime/src/orchestrator_runtime/cli.py` ≥ 1
   e `grep -c "escolha entre" runtime/src/orchestrator_runtime/cli.py` → 0.

## Validação determinística (VAL-001 / VAL-002) — causas-raiz e fixes aplicados

O envelope da tarefa reportou `npm test` e `pytest -q` falhando. Veredito do
validador (`.orchestrator/runtime/results/987c44623b8d/validator-codex.txt:1`):
"npm test falhou: Test-AgentProfiles e Test-NoLegacyArtifacts" / "pytest -q
falhou: 2 testes MCP bloqueados por ORCHESTRATOR_CHILD_AGENT".

| Falha | Causa-raiz | Fix aplicado nesta execução |
|---|---|---|
| `Test-AgentProfiles` | `tests/Test-AgentProfiles.ps1:24-27` exige template == live byte a byte; os 5 profiles live tinham `timeout_default_s` editado (600→2400/1200) sem espelho no template | Já resolvido no workspace antes desta execução: template e live conferidos byte a byte → 6/6 EQUAL (claude, codex, gemini, kimi, opencode, cursor). Nenhuma edição necessária. |
| `Test-NoLegacyArtifacts` | `tests/Test-NoLegacyArtifacts.ps1:45` exige `docs/superpowers` inexistente; a pasta havia sido recriada com plan+spec do rename MCP (2026-07-22), trabalho já concluído (`CHANGELOG.md:62`) | Movidos `docs/superpowers/plans/2026-07-22-mcp-server-name-orchestrator-ia.md` e `docs/superpowers/specs/2026-07-22-mcp-server-name-orchestrator-ia-design.md` para `docs/archive/superpowers/{plans,specs}/`; pasta removida. |
| 2 testes MCP (pytest) | `runtime/src/orchestrator_runtime/mcp/tools.py:337-338` levanta `McpSecurityError` quando `ORCHESTRATOR_CHILD_AGENT` está no ambiente; o dispatch (`scripts/Invoke-RoutedAgent.ps1:109`) seta a var no filho, e a suite herdava — testes não eram herméticos ao ambiente | Fixture autouse em `runtime/tests/conftest.py` (`monkeypatch.delenv("ORCHESTRATOR_CHILD_AGENT")`) — mesmo padrão de isolamento já usado em `tests/Test-DispatchMonitoring.ps1:66`. |

Nota: a execução das suites está bloqueada por permissão nesta sessão
(comandos `npm`/`pytest`/`powershell -File` negados pelo gate); os fixes acima
são derivados do veredito gravado do validador + análise estática com
`arquivo:linha`. Re-execução de `npm test` e `pytest -q` pelo runtime é o
smoke de confirmação.

## Por que não foi aplicado nesta execução

- Mudança no template dispara o checklist completo de version bump
  (`.cursor/rules/version-bump.mdc:10-16`: VERSION, package.json, pyproject,
  CHANGELOG, migração `0.4.6-to-0.4.7.ps1`, docs, propagação `orchestrator
  update -Force` nos consumidores).
- Há mudanças não commitadas do usuário em `.orchestrator/agents/profiles/*.json`
  e `.cursor/rules/version-bump.mdc` (git status) — aplicar+bump agora criaria
  conflito com trabalho em andamento na 0.4.6.
- O patch acima é textual e pronto; aplicação = próxima tarefa curta (bump
  0.4.7) quando a árvore estiver limpa.

## Recomendações priorizadas

| # | Prioridade | Ação |
|---|---|---|
| R1 | P0 | Aplicar Diffs 1-2 (rules template + espelho) com bump 0.4.7 |
| R2 | P0 | Aplicar Diffs 3-5 (docs/adapter + rule embutida em `cli.py:315-352`, F8) no mesmo commit |
| R3 | P1 | Rodar smoke de wording (critério 4) e `orchestrator update -Force` nos consumidores (PrintBee, GuardLine) |
| R4 | P1 | No PrintBee: revisar `printbee-patterns.mdc` — subagentes Cursor não podem ser default; referenciar a rule de modo padrão |
| R5 | P2 | Roadmap: hook determinístico (quando Cursor suportar) que alerte edição inline sem task ativa no runtime |
