# Cleanup report — 0.3.1

**Data:** 2026-07-21  
**Branch:** `feature/call-agent-profiles`  
**Base:** `1171835`  
**Versão:** 0.3.0 → **0.3.1** (patch)

## Diagnóstico

Pós-0.3.0 (runtime + MCP Cursor) restavam prompts bootstrap, specs Superpowers já implementados, um stub de routing sem imports, docs/rules tratando caveman/Cursor como obrigatórios ou `ide-hint`, e `.gitignore` incompleto para artefatos de runtime.

## Removido

| Item | Motivo |
|---|---|
| `runtime/.../routing/registry.py` | Stub morto; zero imports |
| Import não usado `redact` em `mcp/resources.py` | Dead import |

## Arquivado

| De | Para |
|---|---|
| `docs/legacy/prompt_ambiente_multiagente.md` | `docs/archive/prompts/` |
| `docs/superpowers/**` | `docs/archive/superpowers/` |

## Dependências removidas

Nenhuma dependência npm/Python removida (nada comprovadamente órfão no lock/pyproject).

## Preservado

- CLI `dispatch` / `route` (compat)
- Migrations `0.1.0→0.2.0`, `0.2.0→0.3.0`
- Adapters Claude/Codex/Gemini/Kimi/OpenCode/Cursor
- OpenWolf / Graphify / Caveman no catálogo (opt-in)
- `scripts/Backup-Orchestrator.ps1` (utilitário manual)

## Documentação / rules atualizadas

- `model-routing.md`, `orquestrador.md`, `legacy-migration.md`, `repo-layout.md`, `cli-reference.md`, `README.md`
- Skills `call-agent`, `economize-tokens`
- Rule `token-economy.mdc` (template + tracked)
- Inventário: `docs/cleanup/*`
- Índice: `docs/maintenance/legacy-cleanup.md`

## Testes

Ver `validation-baseline.md` e resultados pós-limpeza no commit message / CI local.

## Limitações

- Dogfood `.orchestrator/` local não versionado (exceto arquivos já trackeados por engano histórico — não alterados neste commit).
- Specs arquivados mantêm linguagem histórica (`ide-hint`); código vivo usa `ide-client`.
- Sem migration 0.3.0→0.3.1 (sem mudança de schema).

## Próximos itens

- Avaliar depreciação formal de `dispatch` em minor futura
- CI: garantir `Test-NoLegacyArtifacts` em pipeline remoto
- Revisar skills de orientação vs gates runtime (consolidação docs)
