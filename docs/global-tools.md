# Ferramentas globais (perfil do usuário)

A partir de **0.2.0**, o install/update instala o **núcleo** primeiro. MCPs, plugins, skills e CLIs globais são **opt-in**.

## O que pode ser instalado

Catálogo: [`package/global-tools/catalog.json`](../package/global-tools/catalog.json)

| Tipo | Itens |
|---|---|
| CLI npm (`-g`) | `openwolf`, `firecrawl-cli` |
| CLI uv (`tool install`) | **graphify** (`graphifyy` → `~/.local/bin`) |
| MCP (Claude user + Cursor `~/.cursor/mcp.json`) | Context7, Playwright, Sequential Thinking |
| Plugins Claude (`-s user`) | context7, playwright, superpowers, skill-creator, atlassian, frontend-design, **caveman** |
| Skills (`npx skills add … -g` → `~/.agents/skills`) | obra/superpowers, vercel-labs/skills, firecrawl/cli, terraform-skill, **caveman** |

## Comandos (opt-in)

```bash
# Nucleo apenas (padrao)
orchestrator init
orchestrator update

# Ferramentas globais
orchestrator global-tools
orchestrator init --global-tools

# Init OpenWolf/Graphify no projeto
orchestrator init --init-tools
```

Caveman permanece opcional e está **desabilitado** por padrão no runtime.

Relatório: `.orchestrator/tools/global-status.json`

## Escopo

| Camada | Onde |
|---|---|
| Global | `~/.claude`, `~/.cursor/mcp.json`, `~/.agents/skills`, npm global |
| Workspace | `.orchestrator/mcp/registry.json` (espelho dos MCPs recomendados) |

Credenciais (Atlassian, TestSprite, Google Ads, etc.) **não** são gravadas pelo instalador. Plugins que exigem login (ex.: Atlassian) pedem autenticação no próprio cliente.

## Codex

Plugins oficiais (context7, playwright, superpowers, …) já costumam viver em `~/.codex/config.toml`. O instalador não reescreve esse TOML automaticamente para evitar conflitos; use os plugins Codex já habilitados ou o marketplace oficial.
