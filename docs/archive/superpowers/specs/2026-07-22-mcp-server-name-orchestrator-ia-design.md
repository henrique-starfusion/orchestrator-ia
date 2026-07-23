# Design: renomear MCP Cursor para `orchestrator-ia`

Data: 2026-07-22  
Status: implementado (2026-07-22)  
Abordagem: **A** (chave MCP + `SERVER_NAME` + migração; sem rename de cache/rules)

## Objetivo

Na instalação/configuração do MCP do orquestrador no Cursor, a entrada deve aparecer como **`orchestrator-ia`** em vez de `multiagent-orchestrator`. Instalações existentes devem migrar (nova chave + remoção da antiga) para evitar servidor duplicado.

## Escopo

### Incluído

- Constante canônica `orchestrator-ia` em:
  - `runtime/src/orchestrator_runtime/mcp/cursor_config.py` (`SERVER_KEY`)
  - `runtime/src/orchestrator_runtime/mcp/server.py` (`SERVER_NAME`)
  - `scripts/Configure-CursorMcp.ps1` (merge da chave)
  - `package/template/adapters/cursor/.cursor/mcp.json.example`
- Migração em `merge_mcp_json` e `Merge-CursorMcpFile`:
  1. Escrever/atualizar entrada em `orchestrator-ia`
  2. Remover chave legada `multiagent-orchestrator` se existir
  3. Preservar demais servidores MCP
- Atualizar referências documentais ao **nome do servidor MCP** (README, `docs/mcp-integration.md`, `token-economy.mdc` template/repo, CHANGELOG se aplicável)
- Testes unitários: expect `orchestrator-ia`; cobrir migração da chave antiga

### Fora de escopo

- Renomear path de cache `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator`
- Renomear arquivo de rule `multiagent-orchestrator.mdc`
- Renomear CLI `orchestrator` ou pacote Python

## Comportamento de migração

```
mcp.json existente:
  mcpServers.multiagent-orchestrator = {...}
  mcpServers.other = {...}

após configure/install:
  mcpServers.orchestrator-ia = <entry canônica>
  mcpServers.other = {...}   # intacto
  # multiagent-orchestrator ausente
```

Se só existir `orchestrator-ia`, atualizar in-place (mesmo comportamento de update atual).

## Critérios de aceitação

1. `merge_mcp_json({})` produz chave `orchestrator-ia` (não `multiagent-orchestrator`).
2. Merge com chave legada remove `multiagent-orchestrator` e mantém outros servidores.
3. `Configure-CursorMcp.ps1` e `orchestrator cursor configure` geram o mesmo nome de chave.
4. `SERVER_NAME` do processo MCP é `orchestrator-ia`.
5. Docs que descrevem o servidor MCP na UI/Cursor usam `orchestrator-ia`.
6. Testes relevantes passam.

## Riscos e notas

- Sessões Cursor já conectadas ao MCP antigo podem precisar de reload após a migração do `mcp.json`.
- Regras Cursor (`user-multiagent-orchestrator` no cliente IDE) são namespace do Cursor sobre o server key; após rename, o prefixo MCP nas tools muda para o novo nome — documentar no CHANGELOG.
