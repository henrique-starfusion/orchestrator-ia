# MCP server name `orchestrator-ia` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na instalação/configuração Cursor, a chave MCP e o `SERVER_NAME` passam a ser `orchestrator-ia`, com migração que remove `multiagent-orchestrator` do `mcp.json`.

**Architecture:** Constante única `SERVER_KEY`/`SERVER_NAME` = `orchestrator-ia`. `merge_mcp_json` e `Configure-CursorMcp.ps1` escrevem a nova chave e removem a legada. Docs e testes que citam o **nome do servidor MCP** acompanham; cache path e arquivo `multiagent-orchestrator.mdc` ficam intactos.

**Tech Stack:** Python (runtime MCP), PowerShell (installer), pytest, Markdown docs.

**Spec:** `docs/superpowers/specs/2026-07-22-mcp-server-name-orchestrator-ia-design.md`

## Global Constraints

- Nome canônico do servidor MCP: `orchestrator-ia` (exato)
- Chave legada a remover: `multiagent-orchestrator`
- NÃO renomear `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator`
- NÃO renomear arquivo de rule `multiagent-orchestrator.mdc`
- Critérios de aceitação desta tarefa NÃO são o template genérico de “soma”

---

### Task 1: Testes de merge/migração

**Files:**
- Modify: `runtime/tests/unit/test_mcp_tools.py` (`test_cursor_config_merge` e novo teste de migração)

**Interfaces:**
- Consumes: `merge_mcp_json` de `orchestrator_runtime.mcp.cursor_config`
- Produces: asserts em `orchestrator-ia` + remoção da chave legada

- [x] **Step 1: Atualizar `test_cursor_config_merge`** para esperar `orchestrator-ia` em vez de `multiagent-orchestrator`.

- [x] **Step 2: Adicionar teste de migração**

```python
def test_cursor_config_migrates_legacy_server_key():
    existing = {
        "mcpServers": {
            "multiagent-orchestrator": {"command": "old", "enabled": True},
            "other": {"command": "npx", "args": ["-y", "x"]},
        }
    }
    merged = merge_mcp_json(existing, transport="stdio")
    assert "orchestrator-ia" in merged["mcpServers"]
    assert "multiagent-orchestrator" not in merged["mcpServers"]
    assert "other" in merged["mcpServers"]
```

- [x] **Step 3: Rodar pytest (deve falhar até Task 2)**

Run: `cd runtime && python -m pytest tests/unit/test_mcp_tools.py::test_cursor_config_merge tests/unit/test_mcp_tools.py::test_cursor_config_migrates_legacy_server_key -v`

---

### Task 2: Runtime Python (`SERVER_KEY` / `SERVER_NAME` + migração)

**Files:**
- Modify: `runtime/src/orchestrator_runtime/mcp/cursor_config.py`
- Modify: `runtime/src/orchestrator_runtime/mcp/server.py` (`SERVER_NAME` e docstring)
- Modify: `runtime/src/orchestrator_runtime/cli.py` (help string do mcp_app apenas; paths da rule `.mdc` permanecem)

**Interfaces:**
- Produces: `SERVER_KEY = "orchestrator-ia"`; `merge_mcp_json` remove legado

- [x] **Step 1:** Em `cursor_config.py`, setar `SERVER_KEY = "orchestrator-ia"` e constante `LEGACY_SERVER_KEY = "multiagent-orchestrator"`. Em `merge_mcp_json`, após gravar `servers[SERVER_KEY]`, fazer `servers.pop(LEGACY_SERVER_KEY, None)`.

- [x] **Step 2:** Em `server.py`, `SERVER_NAME = "orchestrator-ia"`.

- [x] **Step 3:** Ajustar help/docstring em `cli.py` que diga “Servidor MCP multiagent-orchestrator” → `orchestrator-ia`.

- [x] **Step 4:** Re-rodar testes da Task 1 — Expected: PASS.

---

### Task 3: PowerShell + template mcp.json

**Files:**
- Modify: `scripts/Configure-CursorMcp.ps1` (bloco merge ~linhas 100–106)
- Modify: `package/template/adapters/cursor/.cursor/mcp.json.example`

- [x] **Step 1:** Introduzir `$McpServerKey = 'orchestrator-ia'` e `$LegacyMcpServerKey = 'multiagent-orchestrator'`. Em `Merge-CursorMcpFile`: gravar `$servers[$McpServerKey] = $ServerEntry`; se `$servers.Contains($LegacyMcpServerKey)` então `$servers.Remove($LegacyMcpServerKey)`.

- [x] **Step 2:** Atualizar `mcp.json.example` com chave `orchestrator-ia`.

- [x] **Step 3:** Manter cópia da rule `multiagent-orchestrator.mdc` (nome de arquivo inalterado).

---

### Task 4: Docs e referências ao nome do servidor MCP

**Files:**
- Modify: `.cursor/rules/token-economy.mdc`
- Modify: `package/template/adapters/cursor/.cursor/rules/token-economy.mdc`
- Modify: `docs/mcp-integration.md`
- Modify: `docs/cursor-integration.md` (se citar nome do servidor MCP; não renomear path da rule)
- Modify: `README.md` (só menções ao nome do servidor MCP na UI, se houver)
- Modify: `CHANGELOG.md` (entrada Unreleased: rename + migração)
- Modify: `docs/runtime-architecture.md`, `docs/archive/prompts/README.md` se citarem o servidor MCP

- [x] **Step 1:** Substituir referências ao **servidor MCP** `multiagent-orchestrator` → `orchestrator-ia`.
- [x] **Step 2:** NÃO alterar paths de cache nem nomes de arquivo `.mdc`.
- [x] **Step 3:** Entrada CHANGELOG sob Unreleased.

---

### Task 5: Verificação final

- [x] **Step 1:** `cd runtime && python -m pytest tests/unit/test_mcp_tools.py -v`
- [x] **Step 2:** Confirmar que `SERVER_NAME` / `SERVER_KEY` / script PS / example JSON usam `orchestrator-ia`.
- [x] **Step 3:** Documentação afetada revisada; validator distinto do executor.
