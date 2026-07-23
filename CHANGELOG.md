# Changelog

## Unreleased

## 0.4.6 — 2026-07-23

### Added

- `role_model_preferences` em `models.json`: papel **planner** prefere **fable** → **opus** (Claude) quando declarados no cliente
- `RulesRouter.resolve_model(..., role=)` aplica preferências por papel antes do `task_map`
- Migration `0.4.5-to-0.4.6`

### Fixed

- Planner recebia Sonnet em tarefas `implementation`/`docs` porque o modelo seguia só o `task_type`

## 0.4.5 — 2026-07-23

### Added

- Orçamento de timeout por papel (`agent_timeout_default_s` / `agent_timeout_by_role` em `policies.json`); executor/corrector padrão **2400s**
- Fallback `git status --porcelain` para popular `changed_files` quando o CLI não reporta
- Issue `AGENT-TIMEOUT` + exclusão de VAL workspace/evidence vazios do `same_issue_repeat_limit` após timeout
- Regra Cursor `version-bump.mdc`: bump semver obrigatório ao entregar mudanças no pacote
- Migration `0.4.4-to-0.4.5`

### Fixed

- Hardcap `min(600, …)` por invocação de agente (tarefas longas morriam em ~10 min mesmo com `maximum_duration_seconds=3600`)
- `ProfileCliAdapter`: `request.timeout_s` passa a prevalecer sobre `profile.timeout_default_s`
- `maximum_duration_seconds` agora encerra o loop quando o tempo restante é insuficiente

### Changed

- Profiles template: `timeout_default_s` 600 → **2400** (CLIs de escrita); gemini **1200**

## 0.4.4 — 2026-07-23

### Added

- MCP chat visibility: `orchestrator_run`/`orchestrator_status` expõem `selected_agents`, `selected_models`, `active_provider`, `active_model`; `message` inclui `provider=`/`model=`; regra Cursor obriga anúncio no chat a cada poll
- Migration `0.4.3-to-0.4.4`

### Fixed

- Codex `models.json`: IDs alinhados a conta ChatGPT (`gpt-5.6-sol`); resolução de tier→modelo concreto; `sandbox_flags` do profile aplicados (`--sandbox workspace-write`, `--skip-git-repo-check`)
- `CliExecutor` usa `stdin=DEVNULL` (evita `codex exec` ficar lendo stdin vazio)
- Repair loop: falha de spawn/CLI do executor não aborta mais em `FAILED` na 1ª iteração — entra em `CORRECTING` (com fallback de executor) até `maximum_iterations`
- Repair loop: testes determinísticos falhos forçam `correct` mesmo se o validator LLM aprovar; issues `TEST-FAIL` vão no prompt do corrector
- Concorrência: `TimeoutError` do WriteLock e double-start MCP **não** marcam a tarefa em andamento como `FAILED`
- CLI adapters usam path absoluto do `detect()` (mitiga WinError 2 / PATHEXT no processo MCP)
- `CliExecutor`: `FileNotFoundError` vira exit 127 em vez de derrubar o workflow
- Acceptance criteria: meta-instruções (`IGNORAR`/`ignore`/`evitar` … função soma) não disparam mais o demo `soma_module`
- Acceptance criteria: auditorias (`complex_analysis`/`security_review`/`architecture`) mantêm ACs de evidência mesmo quando o prompt menciona “testes”/“docs”
- Acceptance criteria: tarefas não-auditoria sempre incluem `workspace_changes` (antes, keywords test/docs omitiam esse AC)
- CLI: `orchestrator agents list` (e `ls`) aceito como alias de `orchestrator agents`
- Teste de regressão Windows: `CliExecutor` resolve `.CMD` via `shutil.which` (PATHEXT / WinError 2)
- Fingerprint MCP: `code_fingerprint` reporta o hash **carregado no processo** (não só o disco); `modules_stale` + warning em `orchestrator_health` quando o disco avançou sem reload

### Changed

- Nome do servidor MCP Cursor: `multiagent-orchestrator` → **`orchestrator-ia`** (install/configure migra `mcp.json` e remove a chave legada; arquivo de rule `multiagent-orchestrator.mdc` e path de cache inalterados)
- Instalação npm/docs passam a usar `#latest` (tag git móvel de release); `github:...@latest` não é suportado pelo npm
- Política de segurança GitHub em `.github/SECURITY.md`; `docs/security.md` atualizado (Orquestrador IA Multiagente)
- Licença do projeto alterada para **MIT** (uso comercial e não comercial por qualquer pessoa)
- GitHub Actions CI desabilitado (sem plano/limite de Actions); workflow preservado em `.github/ci.yml.disabled`
- Notas de Actions movidas de `.github/README.md` para `.github/ACTIONS.md` (GitHub priorizava esse README sobre o da raiz)
- Wrapper Windows `bootstrap-agents.bat` renomeado para `orchestrator-ia.bat`
- Nome do produto padronizado para **Orquestrador IA Multiagente**; docs e URLs apontam para `henrique-starfusion/orchestrator-ia`

## 0.4.3 — 2026-07-22

### Fixed

- MCP stdio: heartbeat/`[exec]` do `CliExecutor` e eventos verbose não escrevem mais em stdout (evita `Unexpected token '[heartbeat]'` no Cursor)
- Logs INFO do SDK MCP silenciados no transporte stdio (menos ruído falso no Output do Cursor)

### Added

- Migration `0.4.2-to-0.4.3`

## 0.4.2 — 2026-07-21

### Added

- CLI `orchestrator agents` (registry JSON/text)
- `orchestrator version` / `-V` / `--version` (com `--json` → fingerprint)
- `orchestrator_health.runtime.code_fingerprint` + `features` (detecta MCP stale)
- Regra Cursor anti-MCP-stale (comparar fingerprint CLI vs MCP após update)
- Migration `0.4.1-to-0.4.2`

### Fixed

- Entry MCP Python alinhada ao PS1 (`cmd /c` + `--project ${workspaceFolder}`)
- Echo live de subprocess aplica `redact()`
- `require_independent_validation` falha se não houver validator ≠ executor
- `fake_agents` rejeitado na superfície MCP
- `.orchestrator/data` com `chmod 0o700` (best-effort)
- Parse de requirements não parte semver (`0.4.1`); auditorias → ACs `evidence`
- `orchestrator analyze` emite `warnings` (`independent_validation_ok`, `validator_equals_planner`)

## 0.4.1 — 2026-07-21

### Added

- Schema tipado de acceptance criteria (`CriterionKind` + `CriterionCheck`) com dispatch no validator
- CI GitHub Actions (pytest + suite PowerShell)
- Migration `0.4.0-to-0.4.1`

### Fixed

- Critérios de aceitação “soma” não disparam mais por substring em `resume`/`summary` (`CriteriaBuilder`)
- Menções negadas (“não criar módulo soma”) não geram AC de soma
- `WriteLock` com reclaim de PID morto e reentrancy (evita deadlock em resume/MCP)
- `orchestrator_delegate` / `orchestrator_analyze` usam `_run_coro` (não quebram no event loop MCP)
- Allowlist MCP estrita (bloqueia workspace externo mesmo com `.orchestrator/`)
- `read_only` enforced em delegate; `allow_network` rejeitado de verdade
- Overrides de agentes respeitados com `routing=automatic`
- Erros em threads background MCP deixam de ser engolidos (log + mark FAILED)

### Changed

- `orchestrator_status` expõe `error`, mensagem legível, agente ativo e ACs
- Regra Cursor `multiagent-orchestrator.mdc` documenta contrato de poll chat↔runtime
- Default `CursorMcpScope=project` (global só com `--cursor-mcp-scope user|both`)
- `DeterministicValidator`: critérios sem verificador exigem evidência (changed_files/tests)
- Critérios legados sem `kind` são migrados por inferência na carga

## 0.4.0 — 2026-07-21

### Added

- Limpeza automática de configurações legadas no `install` / `update` (modo `safe` por padrão)
- Scripts: `Detect|Backup|Migrate|Remove|Validate-LegacyConfigurations`, `Invoke-LegacyCleanupPipeline`, `Restore-LegacyBackup`
- Flags: `--skip-legacy-cleanup`, `--legacy-cleanup-mode safe|aggressive|report-only`, `--keep-legacy-backup`
- Comandos: `orchestrator legacy scan|cleanup|status|restore`
- Relatórios: `legacy-cleanup-report.md`, inventário, state em `runtime/legacy-cleanup-state.json`
- Migration `0.3.1-to-0.4.0`
- Testes de detecção, backup, safe/aggressive/report-only, restore, idempotência e preservação

### Changed

- `Migrate-LegacyClaude.ps1` virou wrapper do pipeline genérico
- CLI Node prefere `python` a `py` no Windows (evita builds free-threaded quebrados)

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
