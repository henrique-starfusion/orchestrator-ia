# Migração legada `.claude/` → `.orchestrator/`

Guia para workspaces que ainda usam `.claude/` como fonte canônica e precisam adotar `.orchestrator/`.

---

## Contexto

Versões anteriores do bootstrap e o prompt `docs/legacy/prompt_ambiente_multiagente.md` orientavam a criar infraestrutura em `.claude/`. A arquitetura atual define **`.orchestrator/` como única fonte canônica**; `.claude/` passa a ser apenas **adaptador fino** para Claude Code.

O instalador detecta legado automaticamente durante `init` / `install` — inclusive quando você usa o one-liner:

```bash
npx --yes github:henrique-starfusion/bootstrap-agents#develop init
```

```powershell
gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/bootstrap-agents/contents/get.ps1?ref=develop" | iex
```

---

## Quando a migração é acionada

Condições em `Install-Orchestrator.ps1`:

```text
Existe:  <projeto>/.claude/VERSION
Ausente: <projeto>/.orchestrator/VERSION
```

Nesse caso, antes de copiar o template, executa `Migrate-LegacyClaude.ps1`.

Se `.orchestrator/VERSION` **já existir**, a migração é ignorada (salvo `-Force`).

---

## O que a migração faz

Script: `scripts/Migrate-LegacyClaude.ps1`

### 1. Backup

Cria bundle em:

```text
.orchestrator/backups/<timestamp>-legacy-migration/
```

Inclui `.claude/` e `.orchestrator/` (se parcialmente existente), com `manifest.json` de checksums.

### 2. Importação seletiva

| Origem | Destino |
|---|---|
| `.claude/memory/` | `.orchestrator/memory/legacy-import/` |
| `.claude/rules/` | `.orchestrator/rules/legacy-import/` |

Pastas ausentes são ignoradas. Destinos existentes são preservados (salvo `-Force`).

### 3. Versão

Grava `.orchestrator/VERSION` com:

- versão do pacote bootstrap, se disponível; senão
- valor de `.claude/VERSION`

### 4. Relatório

Gera:

```text
.orchestrator/runtime/reports/migration-legacy-claude.md
```

### 5. O que **não** faz

- **Não remove** `.claude/` — permanece como adaptador
- **Não migra** automaticamente skills, hooks ou settings JSON completos
- **Não reconstrói** o ambiente do zero

---

## Fluxo recomendado

```text
1. bootstrap-agents.bat install -ProjectPath C:\dev\projeto
      ↓ (migração automática se legado detectado)
2. Revisar .orchestrator/memory/legacy-import/
3. Consolidar conteúdo útil nas pastas canônicas de memory/
4. bootstrap-agents.bat verify -ProjectPath C:\dev\projeto
5. Confirmar adaptador CLAUDE.md / .claude/ apontando para .orchestrator/
```

Simulação:

```bat
bootstrap-agents.bat install -ProjectPath C:\dev\projeto -DryRun
```

Forçar reimportação (cuidado — pode sobrescrever destinos):

```bat
bootstrap-agents.bat install -ProjectPath C:\dev\projeto -Force
```

---

## Pós-migração manual

### Memória

Mova arquivos relevantes de `memory/legacy-import/` para categorias canônicas:

```text
.orchestrator/memory/
├── architecture/
├── decisions/
├── lessons/
├── project/
└── ...
```

Atualize `memory/index.json` se necessário.

### Regras

Conteúdo em `.orchestrator/rules/legacy-import/` deve ser revisado. Políticas ativas ficam em `.orchestrator/config/policies.json`.

### Adaptadores

Após `install`, `Generate-Adapters.ps1` copia `.claude/README.md` e `CLAUDE.md` se Claude estiver `available`. Verifique que os adaptadores referenciam `.orchestrator/`, não duplicam config.

---

## Outros caminhos legados

Pastas como `.codex/`, `.cursor/`, `.agents/` de instalações antigas **não são removidas** automaticamente.

| Flag | Status |
|---|---|
| `-LegacyCleanup` | **Reservada** — limpeza opt-in ainda não implementada no instalador |

Limpeza manual: mova conteúdo útil para `.orchestrator/` ou para backup externo antes de remover duplicatas.

---

## Comparação: legado vs canônico

| Aspecto | Legado | Atual |
|---|---|---|
| Fonte canônica | `.claude/` | `.orchestrator/` |
| VERSION workspace | `.claude/VERSION` | `.orchestrator/VERSION` |
| Primeira instalação | Prompt manual | `bootstrap-agents.bat install` |
| Memória | `.claude/memory/` | `.orchestrator/memory/` |
| Skills | `.claude/skills/` | `.orchestrator/skills/` |
| Prompt de bootstrap | `docs/legacy/prompt_ambiente_multiagente.md` | **Deprecado** |

---

## Rollback

1. Localize backup em `.orchestrator/backups/<timestamp>-legacy-migration/`
2. Restaure `.claude/` a partir do backup se necessário
3. Remova `.orchestrator/` se precisar reverter completamente (com `-Force` no uninstall após backup manual)

```bat
bootstrap-agents.bat uninstall -ProjectPath C:\dev\projeto -DryRun
```

Revise a lista antes de executar sem `-DryRun`.

---

## Perguntas frequentes

**Preciso rodar o prompt legado?**  
Não. Use `bootstrap-agents.bat install -ProjectPath ...`.

**Posso manter `.claude/`?**  
Sim — como adaptador. A configuração compartilhada deve estar em `.orchestrator/`.

**A migração roda no `upgrade`?**  
Não automaticamente. Só no `install` quando `.orchestrator/VERSION` está ausente e `.claude/VERSION` existe.

**E se eu já tiver `.orchestrator/` parcial?**  
O install completa via template + manifest. Migração legada só importa memory/rules se `.orchestrator/VERSION` ainda não existir.

---

## Ver também

- [`installer-architecture.md`](installer-architecture.md)
- [`cli-reference.md`](cli-reference.md)
- [`troubleshooting.md`](troubleshooting.md)
- `package/migrations/README.md` — migrações semver futuras
