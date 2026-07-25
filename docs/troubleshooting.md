# Solução de problemas — Orquestrador IA Multiagente

Guia operacional para falhas comuns do **Orquestrador IA Multiagente** (`@starfusion/orchestrator`).

Quickstart: [`quickstart-oneliner.md`](quickstart-oneliner.md)

---

## Diagnóstico rápido

```bash
orchestrator status
orchestrator verify
orchestrator mcp doctor
orchestrator cursor verify
```

### MCP / Cursor

| Sintoma | Ação |
|---|---|
| Tools MCP ausentes no chat | `orchestrator cursor configure` e reiniciar Cursor |
| `mcp` Python ausente | `pip install -e runtime/` (inclui `mcp>=1.6,<2`) |
| Runtime unavailable | `orchestrator install` no projeto; checar `.orchestrator/` |
| HTTP bind recusado | use `127.0.0.1` ou `ORCHESTRATOR_MCP_ALLOW_REMOTE=1` |
| `Unexpected token '[heartbeat]'` / `transport_error` | stdout poluido no stdio; atualize o runtime (heartbeat em stderr) e **reload Cursor** |
| Log `[error] INFO Processing request` + `undefined` | Cosmetico: Cursor trata stderr como erro; conexao OK se houver `Successfully connected` |

```bat
orchestrator-ia.bat status -ProjectPath C:\dev\projeto
orchestrator-ia.bat verify -ProjectPath C:\dev\projeto
orchestrator-ia.bat analyze -ProjectPath C:\dev\projeto
```

Logs:

```text
.orchestrator/runtime/validations/*.log
.orchestrator/runtime/reports/installation-report.md
```

Cache do one-liner PowerShell:

```text
%LOCALAPPDATA%\StarFusion\multiagent-orchestrator
```

---

## 0.4.19 — Duas tasks no mesmo projeto ao mesmo tempo

**Sintoma (antes):** segunda `orchestrator_run` competia pelo WriteLock, ficava `RECEIVED` com `blocked_by_lock` ou parecia travada; chat cancelava.

**Comportamento (0.4.19):** 1 execução ativa por `project_path`. Nova submissão → status `QUEUED`, campos `queue_position` e `blocked_by`. Ao terminar/cancelar a ativa, a próxima da fila inicia sozinha (FIFO). Projetos diferentes não se bloqueiam.

**Poll:** `orchestrator_status` mostra `Estado: QUEUED | fila pos=N blocked_by=<id>`.

## 0.4.16 — Tasks RECEIVED que nunca iniciam (zumbis de sessão anterior)

**Sintoma:** `orchestrator task list` mostra tasks RECEIVED antigas que nunca transitaram para ANALYZING. O chat tentou rodar mas a sessão foi perdida antes do dispatch.

**Causa:** Tasks RECEIVED sem lock ficam "mudas" — o processo que devia executá-las morreu. O orquestrador não as cancela automaticamente (antes de 0.4.16).

**Solução (0.4.16):** Auto-cancel de tasks RECEIVED com idade > `stale_received_ttl_hours` (padrão: 6h). Disparado automaticamente em `create_task`. Configurável em `policies.json`:

```json
{ "stale_received_ttl_hours": 6 }
```

---

## 0.4.16 — Task classificada incorretamente como "docs"

**Sintoma:** Prompt de implementação (ex.: "Criar/atualizar regras de produção") é classificado como `docs`, gerando ACs de evidência/análise em vez de workspace_changes.

**Causa:** O check de "doc" era substring, podendo casar falsamente em outros contextos. Além disso, prompts com intent de implementação E keyword "doc"/"documentação" ficavam presos como "docs".

**Solução (0.4.16):** Check usa `\bdoc` (word-boundary); prompts com verbo de implementação + keyword docs são promovidos para `implementation` (mesmo padrão do `complex_analysis`).

---

## 0.4.16 — `InvalidTransitionError: RETRIEVING_MEMORY -> RETRIEVING_MEMORY` (double-resume/MCP retry)

**Sintoma:** Task transita para FAILED com mensagem `Transição inválida: RETRIEVING_MEMORY -> RETRIEVING_MEMORY`. Ocorre quando o MCP faz retry de `orchestrator_run` ou quando o resume é chamado duas vezes na mesma task.

**Causa:** `assert_transition` não era idempotente — mesmo estado levantava `InvalidTransitionError`.

**Solução (0.4.16):** `assert_transition(same, same)` é no-op; `repo.transition(task, same_state, ...)` retorna sem salvar nem emitir evento.

---

## 0.4.16 — Duas tasks paralelas competem pelo workspace (PrintBee: 2 tabs simultâneos)

**Sintoma:** Uma das tasks completa normalmente; a outra trava em RECEIVED ou aparece com `error: Lock em uso por outra task asyncio`. Em versões anteriores a segunda task entrava no loop como se tivesse o lock (reentrância incorreta).

**Causa:** `WriteLock.acquire()` permitia a segunda task asyncio reentrar via `_depth` quando `_held=True`, pois não rastreava qual task asyncio detinha o lock. Spinning no event loop causaria deadlock.

**Solução (0.4.16):** `WriteLock` rastreia `_owner_task` (asyncio Task). Segunda task ≠ owner → `TimeoutError` imediato → `run_task` registra `blocked_by_lock` e retorna sem FAILED na task em andamento.

---

## One-liner / CLI npm

### Acentos somem ou viram `�` / `?` no Cursor ou PowerShell

**Sintoma:** `correção` aparece como `correo`/`corre��o`, `botões` como `botes`/`bot�es`, ou a descrição termina no meio de uma palavra.

**Causa até 0.4.6:** o Python herdava CP1252 em pipes Windows e a CLI emitia bytes CP1252; consumidores Cursor/Node os decodificavam como UTF-8. Além disso, `task list` cortava o prompt silenciosamente em 60 caracteres. A entrada MCP e o SQLite não alteravam o texto.

**Solução:**

1. Atualize o pacote/runtime para 0.4.7 ou superior.
2. Reinicie o MCP/recarregue a janela do Cursor para descartar o processo antigo.
3. Use `orchestrator task list --json` quando precisar do prompt integral; a saída texto é um preview explícito com `…`.

Registros antigos não exigem migração se o prompt armazenado no SQLite estiver correto; o defeito era na saída. O runtime 0.4.7 fixa UTF-8 nos streams antes de Typer/FastMCP escreverem.

---

### `npx` pede autenticação ou falha no clone

**Causa:** repositório privado sem credencial Git configurada.

**Solução:**

1. `gh auth login` (HTTPS ou SSH)
2. Confirme `git ls-remote https://github.com/henrique-starfusion/orchestrator-ia.git`
3. Repita: `npx --yes github:henrique-starfusion/orchestrator-ia#latest init`

---

### `PowerShell nao encontrado` (CLI Node)

**Causa:** `bin/orchestrator.js` não achou `powershell.exe` / `pwsh`.

**Solução:** use Windows PowerShell 5.1+ ou instale PowerShell 7 e garanta que estejam no PATH.

---

### `gh api ... | iex` falha com 404 / Bad credentials

**Causa:** sem login no GitHub CLI, branch inexistente ou token sem escopo `repo`.

**Solução:**

```powershell
gh auth status
gh auth refresh -s repo
gh api repos/henrique-starfusion/orchestrator-ia --jq .full_name
```

---

### Cache corrompido após `get.ps1`

**Causa:** clone incompleto em `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator`.

**Solução:**

```powershell
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\StarFusion\multiagent-orchestrator"
# rode o one-liner novamente, ou:
.\get.ps1 -ForceRefresh
```

---

### `orchestrator` / `mao` não reconhecido após npm global

**Causa:** pasta de bins do npm fora do PATH.

**Solução:**

```bash
npm prefix -g
npm bin -g
# adicione o caminho de bin ao PATH e reabra o terminal
npm install -g github:henrique-starfusion/orchestrator-ia#latest
```

---

## Erros de preflight (Detect-Environment)

### `PowerShell 5.1 ou superior e obrigatorio`

**Causa:** versão antiga do PowerShell.

**Solução:** use Windows PowerShell 5.1+ ou PowerShell 7+ (`powershell.exe` invocado pelo BAT).

---

### `git nao encontrado no PATH`

**Causa:** Git não instalado ou fora do PATH.

**Solução:** instale [Git for Windows](https://git-scm.com/) e reinicie o terminal.

---

### `Integridade do pacote`

**Causa:** arquivos ausentes em `package/` (manifest, template, sources).

**Solução:**

- Confirme clone/cópia completa do repositório orchestrator-ia
- Se veio via npm/npx, reinstale o pacote (`npx` limpa cache com `--yes` / limpe npm cache se necessário)
- Se veio via `get.ps1`, force refresh do cache (`-ForceRefresh`)
- Verifique `package/manifest.json` e `package/template/.orchestrator/`
- Não edite `checksums.json` manualmente sem regenerar

---

### `Sem permissao de escrita no projeto`

**Causa:** ACL, pasta somente leitura ou projeto em local protegido.

**Solução:** execute em diretório gravável ou ajuste permissões NTFS.

---

### `Espaco livre insuficiente`

**Causa:** menos de 50 MB livres no volume do projeto.

**Solução:** libere espaço em disco.

---

### `Lock de instalacao ja existe`

**Causa:** arquivo `.orchestrator/runtime/install.lock` presente.

**Solução:**

1. Confirme que nenhum `install` está em execução
2. Se lock órfão, remova manualmente `install.lock`
3. Reexecute o comando

---

## Erros de versão

### `Workspace mais novo que o pacote` (exit 6)

**Causa:** `.orchestrator/VERSION` > `VERSION` na raiz do pacote orchestrator-ia.

**Solução:**

- Atualize o pacote orchestrator-ia para versão ≥ workspace
- **Não** force downgrade sem backup

---

### `Comparacao de versao invalida` (upgrade)

**Causa:** VERSION malformado (não semver).

**Solução:** corrija `.orchestrator/VERSION` para formato `MAJOR.MINOR.PATCH` ou use `-Force` conscientemente.

---

## Erros de validação

### `.orchestrator ausente`

**Solução:**

```bat
orchestrator-ia.bat install -ProjectPath C:\dev\projeto
```

---

### `Arquivo gerenciado ausente`

**Causa:** remoção manual de arquivos do manifest (modo `managed`).

**Solução:**

```bat
orchestrator-ia.bat repair -ProjectPath C:\dev\projeto
```

---

### `JSON invalido` em config ou registry

**Causa:** edição manual corrompeu JSON.

**Solução:**

1. Identifique o arquivo no log de validação
2. Restaure de `.orchestrator/backups/` ou git
3. Rode `repair` se necessário

---

## Agentes

### Codex trava em VALIDATING / processo fica preso por 10–20 min no Windows

**Sintoma A (sandbox 740):** tarefa fica em VALIDATING/EXECUTING; log com `CreateProcessAsUserW failed: 740` / `windows sandbox: runner failed`.

**Sintoma B (subagentes / printbee-patterns, 0.4.18):** sandbox já é `danger-full-access`, mas o log cresce para MB com `collab: Wait`, `command timed out after 124`, menções a “três subagentes” / `printbee-patterns`. O Codex entra em loop de wait em vez de implementar inline.

**Causa:** o profile padrão do Codex usa `--sandbox workspace-write`, que no Windows exige que `CreateProcessAsUserW` crie um processo restrito — operação que requer elevação de privilégio (erro 740 = `ERROR_ELEVATION_REQUIRED`). O Codex **não aborta** ao receber esse erro; em vez disso, tenta novamente via MCP `node_repl/js` indefinidamente.

Mecanismos:

1. **Override sandbox Windows (0.4.15):** `workspace-write` → `danger-full-access` em `os.name == "nt"`.
2. **Fail-fast 740 (0.4.15):** após N marcadores 740 no stream, mata o processo (`agent_infra_fail_fast_count`).
3. **Restrição child always-on (0.4.18):** prompt do executor/validator/planner **sempre** proíbe spawn/collab/Wait e ignora rito de N subagentes (não depende mais da env no processo MCP).
4. **Fail-fast collab (0.4.18):** marcadores `collab: wait` e `command timed out after 124` também disparam INFRA-FAIL-FAST.

**Solução (em caso de install anterior a 0.4.15):**

```bash
orchestrator update --force
```

**Verificação:**

```bash
# Confirme que o runtime é 0.4.15+:
orchestrator status
# Deve listar features: codex_infra_failfast, codex_sandbox_windows_override
```

**Ajuste de sensibilidade** (se 3 for alto/baixo demais):

```json
# .orchestrator/config/policies.json
{ "agent_infra_fail_fast_count": 2 }
```

**Nota:** o erro 740 não é um problema de mérito — o agente simplesmente não consegue inicializar o sandbox. O runtime trata isso como `validator_infra_failure` e nunca converte em rejeição de AC.

---

### Nenhum agente detectado

**Causa:** CLIs não estão no PATH.

**Solução:**

1. Instale o CLI desejado (ex.: Claude Code, Codex)
2. Abra novo terminal
3. `orchestrator-ia.bat analyze -ProjectPath ...`

Registro: `.orchestrator/agents/detected.json`

---

### Agente `installed_failed`

**Causa:** binário encontrado, mas `--version` falhou ou timeout.

**Solução:** teste manualmente no terminal (`claude --version`, etc.). Reinstale o CLI se corrompido.

---

### Adaptador não criado

**Causa:** agente detectado sem template de adaptador (ex.: `aider`, `goose`).

**Solução:** normal — só vendors mapeados recebem adaptador. Config canônica ainda funciona via `.orchestrator/`.

---

### Update de CLIs de agentes falhou

**Causa:** `claude|codex|kimi update`, `npm install -g`, `choco upgrade` ou `scoop update` retornou erro.

**Solução:** avisos não bloqueiam install/update. Veja `.orchestrator/runtime/reports/agent-updates.json`. Atualize o CLI manualmente ou use `-SkipAgentUpdates` / `--skip-agent-updates` para pular a etapa.

---

## Ferramentas opcionais

### `OpenWolf nao encontrado` / `Graphify nao encontrado`

**Esperado** se não instalados. Não bloqueia install.

**Solução (opcional):** instale as ferramentas e reexecute install ou `analyze`.

Use `-SkipTools` para suprimir a etapa.

---

### `uv tool upgrade graphifyy falhou`

**Causa:** Graphify não instalado via uv ou nome de pacote indisponível.

**Solução:** aviso apenas. Instale Graphify manualmente se necessário.

---

## MCP

### Context7 não conecta

**Causa:** registrado com `enabled: false` por padrão.

**Solução:** edite `.orchestrator/mcp/registry.json`, defina `enabled: true` após configurar credenciais/ambiente.

---

## Migração legada

### Conteúdo duplicado após migração

**Causa:** `.claude/memory` importado para `legacy-import/` enquanto `.claude/` permanece.

**Solução:** consolide manualmente em `.orchestrator/memory/` e documente decisões em `memory/decisions/`.

Veja [`legacy-migration.md`](legacy-migration.md).

---

## Uninstall

### Arquivos adaptadores permanecem

**Esperado:** `uninstall` remove entradas do manifest em `.orchestrator/`, não `CLAUDE.md` ou `.cursor/` na raiz.

**Solução:** remova adaptadores manualmente se desejar.

---

### `-Force` remove tudo

**Causa:** `-Force` no uninstall apaga `.orchestrator/` inteiro.

**Solução:** sempre revise backup em `.orchestrator/backups/*-pre-uninstall/` antes.

---

## Limpeza de legado e flags

Limpeza automática: [`legacy-cleanup.md`](legacy-cleanup.md).

| Flag / comando | Status |
|---|---|
| `--skip-legacy-cleanup` / `--legacy-cleanup-mode` | Implementado (0.4.0+) |
| `orchestrator legacy restore --backup <id>` | Implementado |
| `-InstallMissingAgents` | Não implementado |
| `-RunProjectTests` | Não implementado |

---

## Simulação (DryRun)

```bat
orchestrator-ia.bat install -ProjectPath C:\dev\projeto -DryRun
orchestrator-ia.bat upgrade -DryRun
```

Útil para preview sem lock nem escrita.

---

## Coleta de evidências para suporte

Inclua:

1. Saída completa do comando com erro
2. `orchestrator-ia.bat status -ProjectPath ...`
3. Último log em `.orchestrator/runtime/validations/`
4. `installation-report.md`
5. Versões: `VERSION` (pacote) e `.orchestrator/VERSION`

---

## Ver também

- [`cli-reference.md`](cli-reference.md)
- [`installer-architecture.md`](installer-architecture.md)
- [`legacy-migration.md`](legacy-migration.md)
