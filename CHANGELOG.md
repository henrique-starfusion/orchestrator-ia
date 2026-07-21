# Changelog

## 0.3.1 — 2026-07-21

### Removed / archived

- Prompt bootstrap legado movido para `docs/archive/prompts/`
- Specs/planos Superpowers movidos para `docs/archive/superpowers/`
- Stub morto `runtime/.../routing/registry.py` (não referenciado)

### Changed

- Caveman/documentação: opcional (não obrigatório); Cursor preferindo MCP a `Task`
- Skill `economize-tokens` e rule `token-economy.mdc` alinhadas ao runtime
- `.gitignore` ampliado (runtime DB, `.wolf/`, `.ai/`, caches, secrets)
- Teste anti-legado `Test-NoLegacyArtifacts.ps1`

### Preserved

- `dispatch`, migrations, adapters, `Backup-Orchestrator.ps1` (utilitário manual)
- OpenWolf/Graphify como opt-in

## 0.3.0 — 2026-07-21

### Added

- Servidor MCP **`multiagent-orchestrator`** (`orchestrator mcp serve`)
- Tools: health, analyze, delegate, run, status, events, result, cancel, resume, message, agents, memory_search
- Resources `orchestrator://…` e prompts MCP reutilizáveis
- Comandos `orchestrator cursor configure|verify|print-config`
- Rule Cursor `multiagent-orchestrator.mdc` (front controller)
- Merge seguro de `.cursor/mcp.json` (stdio/http)
- Flags instalador: `--configure-cursor-mcp`, `--cursor-transport`, `--skip-cursor`
- Docs: `mcp-integration.md`, `cursor-front-controller.md`, `human-approval-flow.md`, `mcp-tool-reference.md`, `api.md`, `security.md`

### Changed

- Cursor permanece cliente IDE; chat (qualquer modelo) é front controller via MCP
- Manager/Rules continua escolhendo CLIs no workflow (`routing=automatic`)

## 0.2.0 — 2026-07-21

### Added

- **Runtime persistente** Python (`runtime/`) com SQLite em `.orchestrator/data/orchestrator.db`
- Comandos: `orchestrator run`, `orchestrator task create|run|status|list|cancel|resume|logs|artifacts`
- Máquina de estados completa (RECEIVED → … → COMPLETED/INCOMPLETE/FAILED)
- Adapters Claude/Codex (MVP) + Gemini/Kimi/OpenCode (experimental) + Cursor como `ide-client`
- Manager model: `RulesManager` (default) + hook `openai-compatible` opcional
- Discovery/execução de testes determinísticos
- Validação independente + completion gate + documentation gate
- Memória operacional (episódios, performance de agente/estratégia)
- Docs: `runtime-architecture.md`, `task-lifecycle.md`, `agent-adapters.md`, `manager-model.md`, `memory-and-learning.md`, `cursor-integration.md`, `documentation-policy.md`

### Changed

- Instalação **núcleo primeiro**: OpenWolf/Graphify/MCPs/plugins/skills globais são **opt-in** (`--init-tools`, `--global-tools` / `orchestrator global-tools`)
- Caveman desabilitado por padrão no runtime e policies
- `dispatch --client cursor` deprecado (orientação para `orchestrator run`)
- Skills/adapters atualizados para runtime + gate documental

### Compatibility

- Comandos de instalador (`install`, `update`, `verify`, `repair`, …) preservados
- `route` / `dispatch` preservados; despacho de processo alinhado ao `CliExecutor` do runtime

## 0.1.0

- Instalador versionado, template `.orchestrator/`, global-tools, route/dispatch, profiles
