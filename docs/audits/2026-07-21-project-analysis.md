# Auditoria do projeto — bootstrap-agents / @starfusion/orchestrator

**Data:** 2026-07-21  
**Versão auditada:** 0.4.0  
**Escopo:** arquitetura, runtime MCP, installer, testes, docs, segurança, DX  
**Método:** health/status CLI + MCP; tentativa `orchestrator_run` (falhas reais); exploração read-only; `pytest` + `npm test`

---

## Resumo executivo

O produto está funcional para install/verify/MCP health e tem boa base de testes (37 pytest OK; 24/25 PS). Porém o **runtime de orquestração em produção ainda carrega heurísticas de demo** e tem **falhas de concorrência/segurança na superfície MCP** que impedem análises reais de completar de forma confiável.

Durante esta auditoria:

| Tentativa | Task ID | Resultado |
|-----------|---------|-----------|
| `orchestrator_run` #1 | `6e184e21b4e6` | **FAILED** — timeout no `WriteLock` após `resume` enquanto planner ainda rodava |
| `orchestrator_run` #2 | `7cbc38fd181f` | Travado longo em `SELECTING_AGENTS` (planner Claude); gerou artefato em path legado `docs/superpowers/` |
| Critérios gerados | ambas | AC de **“função soma”** apesar do prompt ser auditoria (bug `sum` ⊆ `resume`) |

---

## Achados críticos

### C1 — Allowlist MCP permissiva (cross-project)

- **Evidência:** `runtime/src/orchestrator_runtime/mcp/tools.py:55-76`
- **Problema:** workspace absoluto fora do cwd é aceito se existir `.orchestrator/`.
- **Impacto:** cliente MCP pode operar em outros projetos do disco.
- **Docs divergentes:** `docs/security.md:8` sugere allowlist cwd/projeto.
- **Recomendação:** allowlist estrita (`default_workspace` + lista explícita); rejeitar paths externos; teste de regressão.

### C2 — Critérios de aceitação “soma” por substring `sum`

- **Evidência:** `runtime/src/orchestrator_runtime/planning/analyzer.py:104-106`
- **Root cause:** `if "soma" in lowered or "sum" in lowered` — `"sum" in "resume"` é `True`.
- **Prova runtime:** tasks `6e184e21b4e6` / `7cbc38fd181f` receberam AC-001/002 de soma com prompt contendo `resume/cancel`.
- **Impacto:** gates de validação medem demo, não o objetivo; tarefas legítimas falham ou desviam.
- **Recomendação:** word-boundary / tokens (`\bsoma\b`, `\bsum\b`); extrair ACs do prompt do usuário; testes com prompts contendo `resume`, `summary`, `assumption`.

---

## Achados altos

### A1 — `WriteLock` sem reentrancy nem stale-PID

- **Evidência:** `runtime/src/orchestrator_runtime/execution/locks.py:17-35`; `tasks/service.py:144-145`, `168-172`
- **Problema:** lock file exclusivo; `resume`/`run` concorrente falha em 30s; PID morto deixa lock órfão; mesma sessão MCP não é reentrante.
- **Prova:** task `6e184e21b4e6` → `Não foi possível obter lock: ...\workspace.write.lock`
- **Recomendação:** reentrancy por PID; reclaim se PID morto; fila de tasks; não chamar `resume` enquanto `_execute_loop` ainda segura o lock.

### A2 — `fake_agents` exposto na tool MCP `orchestrator_run`

- **Evidência:** `mcp/tools.py:276-278`, `mcp/schemas.py`, `agents/base_adapters.py` (FakeAgent escreve arquivos)
- **Impacto:** chat pode forçar adapters fake que escrevem no workspace.
- **Recomendação:** remover da superfície MCP; só via env de teste + não-stdio.

### A3 — `ORCHESTRATOR_FAKE_AGENTS` ativa fake no MCP Cursor

- **Evidência:** `mcp/tools.py:45-50`
- **Recomendação:** ignorar env em transporte MCP stdio de produção; warning explícito.

### A4 — `read_only` em `orchestrator_delegate` ignorado

- **Evidência:** `mcp/schemas.py:23`; `mcp/tools.py:177-219` — parâmetro nunca enforced; sempre `adapter.run(...)`.
- **Impacto:** cliente acredita em delegação read-only; agente pode escrever.
- **Recomendação:** rejeitar roles de escrita ou passar sandbox/profile read-only.

### A5 — Sem CI/CD (`.github/`)

- **Evidência:** zero workflows; `package.json` tem `test` / `test:runtime`.
- **Impacto:** regressões (incluindo security) não bloqueiam PR.
- **Recomendação:** GA em Windows: `npm run test:runtime` + `tests/Run-AllTests.ps1` em PRs para `develop`.

### A6 — Install/update muta `~/.cursor/mcp.json` por default

- **Evidência:** `Install-Orchestrator.ps1` / `Configure-CursorMcp.ps1` — `CursorMcpScope = 'both'`
- **Impacto:** side-effect global sem opt-in explícito.
- **Recomendação:** default `project`; global só com flag.

### A7 — `routing=automatic` descarta overrides de agentes do payload

- **Evidência:** `mcp/tools.py:266-288` só aplica `planner`/`executor`/`validator` do request quando `routing != "automatic"`. Com default `routing=automatic`, a task `7cbc38fd181f` (validator=opencode no payload) ainda planejou `validator: claude`.
- **Impacto:** cliente MCP acredita ter escolhido validador independente; policy colapsa no mesmo agente.
- **Recomendação:** overrides explícitos devem ter precedência sobre automatic; falhar se validator == executor quando policy exige independência.

### A8 — Planner Claude recriou path legado `docs/superpowers/`

- **Evidência:** durante task `7cbc38fd181f` surgiu `docs/superpowers/plans/2026-07-21-project-audit.md`
- **Impacto:** quebra `Test-NoLegacyArtifacts` (“docs/superpowers deve ter sido arquivado”).
- **Mitigação nesta auditoria:** plan movido para `docs/archive/superpowers/plans/`; dir legado removido → teste PASS.
- **Recomendação:** prompt do planner deve citar paths canônicos (`docs/audits/`); policy anti-paths legados no sandbox.

### A9 — `orchestrator_delegate` quebra com event loop asyncio

- **Evidência:** chamada MCP `orchestrator_delegate` → `asyncio.run() cannot be called from a running event loop` (`mcp/tools.py:219` usa `asyncio.run(adapter.run(...))` dentro do server async).
- **Impacto:** delegação pontual via MCP fica inutilizável no transporte stdio assíncrono.
- **Recomendação:** `await adapter.run(...)` (tornar `delegate` async) ou `asyncio.get_event_loop().create_task` / `asyncio.run_coroutine_threadsafe`.

---

## Achados médios

### M1 — Suite PS: `Test-NoLegacyArtifacts` sensível a recriação de legado

- **Evidência:** `npm test` inicial → 24 PASS / 1 FAIL enquanto `docs/superpowers` existia; após arquivar → PASS.
- **Recomendação:** manter só `docs/archive/superpowers/`; bloquear recriação por agentes (ligado a A8).

### M2 — Redact incompleto (echo live + padrões fracos)

- **Evidência:** `agents/process.py` — echo stdout/stderr sem redact; padrões só `KEY=value`.
- **Recomendação:** redact no live stream; cobrir Bearer/JWT/`sk-`.

### M3 — `allow_network` documentado como bloqueado, no-op no código

- **Evidência:** `mcp/tools.py:260-262` (`pass`); `docs/security.md:14`
- **Recomendação:** `McpSecurityError` se `True`, ou implementar sandbox.

### M4 — Três geradores divergentes de `.cursor/mcp.json`

- **Evidência:** `mcp/cursor_config.py` vs `Configure-CursorMcp.ps1` vs `.cursor/mcp.json` tracked
- **Recomendação:** uma função canônica; templates alinhados.

### M5 — `repair` não regenera MCP/adapters/hooks

- **Evidência:** `Repair-Orchestrator.ps1` vs `verify` em `Install-Orchestrator.ps1`
- **Recomendação:** flags de repair completo ou docs honestas.

### M6 — `docs/agent-environment.md` referenciado, não instalado

- **Evidência:** rules/README apontam o arquivo; real em `package/template/docs/`; ausente do `manifest.json`
- **Recomendação:** incluir no manifest ou corrigir links.

### M7 — CLI `orchestrator agents` inválido no installer PS

- **Evidência:** `Install-Orchestrator.ps1:5` ValidateSet sem `agents`; help MCP lista `orchestrator_agents`; wrapper Node roteia mal.
- **Recomendação:** mapear `agents` → runtime MCP/health ou remover do help.

### M8 — SQLite/`data/` sem hardening de permissões

- **Evidência:** `memory/database.py`, `config.py` — mkdir sem `0o700`
- **Recomendação:** permissões restritas + doc multi-usuário.

### M9 — Exceções engolidas em threads background MCP

- **Evidência:** `mcp/tools.py` ~325-329, 457-461, 488-492 (`except Exception: pass`)
- **Recomendação:** log + evento FAILED.

### M10 — Validator e executor podem ser o mesmo agente (Claude)

- **Evidência:** plan padrão `planner=claude`, `validator=claude` em `execute_review_repair`
- **Conflito:** policy de validação independente / regra Cursor.
- **Recomendação:** forçar validator ≠ executor quando ≥2 agentes available.

---

## Achados baixos

| ID | Achado | Evidência |
|----|--------|-----------|
| B1 | Flags `-InstallMissingAgents` / `-RunProjectTests` só viram “limitations” | `Install-Orchestrator.ps1:743-748` |
| B2 | `orchestrator tools` só imprime INFO | `bin/orchestrator.js:263-267` |
| B3 | ValidateSet de clients incompleto vs detecção (~20 CLIs) | installer vs README |
| B4 | Teste placeholder `assert True` | `runtime/tests/unit/test_mcp_tools.py` |
| B5 | Comentário enganoso em `sanitize_env` | `agents/process.py` |
| B6 | Heurística de task_type frágil (keyword match) | `planning/analyzer.py:47-54` |

---

## Resultados de testes (evidência)

### `python -m pytest` (runtime)

```
37 passed in 11.44s
```

### `npm test` (PowerShell)

```
Total: 25 | Passed: 24 | Failed: 1
FAIL: Test-NoLegacyArtifacts   # causa: docs/superpowers recriado pelo planner
```

Após arquivar o leftover nesta auditoria: `Test-NoLegacyArtifacts` → **PASS**.

### MCP health (amostra)

- status: `healthy`, runtime 0.4.0, DB presente
- agentes available: claude, codex, kimi, opencode
- warning: gemini unavailable
- `orchestrator cursor verify`: `ok: true`

---

## Quick wins (ordem sugerida)

1. Corrigir `CriteriaBuilder` (word boundaries) + testes com `resume`/`summary`.
2. Corrigir `delegate` async (`asyncio.run` → `await`) — A9.
3. Stale-PID + reentrancy no `WriteLock`; serializar resume.
4. Enforçar `read_only` no delegate; tirar `fake_agents` do MCP.
5. Restringir allowlist de workspace.
6. Adicionar GitHub Actions mínima.
7. Default `CursorMcpScope=project`.
8. Overrides explícitos com precedência sobre `routing=automatic`; validator ≠ executor.

## Melhorias estruturais

1. Manager model real (LLM) para ACs/estratégia — sair do rules-only de demo.
2. Fila de tasks + worker fora do processo MCP stdio (evita lock/long-poll no mesmo PID).
3. Sandbox de escrita por role + política anti-paths legados.
4. Unificar geração de adapters/MCP (PS ↔ Python).
5. Observabilidade: eventos estruturados, métricas de duração por fase, alertas de stuck state.

---

## Mapa rápido da arquitetura

| Área | Papel |
|------|--------|
| `.orchestrator/` | Config canônica, memória, DB, runtime artifacts |
| `runtime/` | Task service, MCP, agents, planning, validation |
| `package/` | Template + manifest do installer |
| `scripts/` | Install/update/verify/repair/legacy (PowerShell) |
| `bin/orchestrator.js` | Front CLI Node → PS ou Python |
| Adapters (`.cursor`, `.claude`, …) | Gerados/merged a partir do template |

Cursor deve permanecer **cliente IDE**, não worker (`cursor.kind=ide-client`).

---

## Registro documental

```json
{
  "required": true,
  "reason": "Auditoria completa solicitada; gaps/falhas/melhorias documentados",
  "files_updated": [
    "docs/audits/2026-07-21-project-analysis.md"
  ],
  "files_reviewed": [
    "runtime/src/orchestrator_runtime/planning/analyzer.py",
    "runtime/src/orchestrator_runtime/execution/locks.py",
    "runtime/src/orchestrator_runtime/mcp/tools.py",
    "runtime/src/orchestrator_runtime/tasks/service.py",
    "scripts/Install-Orchestrator.ps1",
    "docs/security.md",
    "tests/Test-NoLegacyArtifacts.ps1",
    "bin/orchestrator.js"
  ],
  "validation": "passed — opencode (validator CLI) confirmou C1-C2 e A1-A9; A7 corrigido no relatório após divergência parcial (causa = routing=automatic)"
}
```

---

## Próximo passo recomendado

Abrir implementação focada nos quick wins 1–5 (sem expandir escopo), com PR para `develop` e CI mínima no mesmo PR.
