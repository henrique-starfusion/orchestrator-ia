# Solução de problemas

Guia operacional para falhas comuns do instalador **bootstrap-agents** / **@starfusion/orchestrator**.

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

## One-liner / CLI npm

### `npx` pede autenticação ou falha no clone

**Causa:** repositório privado sem credencial Git configurada.

**Solução:**

1. `gh auth login` (HTTPS ou SSH)
2. Confirme `git ls-remote https://github.com/henrique-starfusion/bootstrap-agents.git`
3. Repita: `npx --yes github:henrique-starfusion/bootstrap-agents#develop init`

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
gh api repos/henrique-starfusion/bootstrap-agents --jq .full_name
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
npm install -g github:henrique-starfusion/bootstrap-agents#develop
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

- Confirme clone/cópia completa do repositório bootstrap-agents
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

**Causa:** `.orchestrator/VERSION` > `VERSION` na raiz do pacote bootstrap.

**Solução:**

- Atualize o pacote bootstrap-agents para versão ≥ workspace
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

### `-UpdateAgents` falhou

**Causa:** `claude update` / `codex update` / npm retornou erro.

**Solução:** avisos não bloqueiam install. Atualize CLIs manualmente.

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
