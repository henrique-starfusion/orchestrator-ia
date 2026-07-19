# Ferramentas globais (perfil do usuário)

O Orquestrador instala um núcleo de **MCPs, plugins, skills e CLIs no perfil do usuário**, para reutilizar em vários projetos — não só no workspace atual.

## O que é instalado

Catálogo: [`package/global-tools/catalog.json`](../package/global-tools/catalog.json)

| Tipo | Itens |
|---|---|
| CLI npm (`-g`) | `openwolf`, `firecrawl-cli` |
| CLI uv (`tool install`) | **graphify** (`graphifyy` → `~/.local/bin`) |
| MCP (Claude user + Cursor `~/.cursor/mcp.json`) | Context7, Playwright, Sequential Thinking |
| Plugins Claude (`-s user`) | context7, playwright, superpowers, skill-creator, atlassian, frontend-design, **caveman** |
| Skills (`npx skills add … -g` → `~/.agents/skills`) | obra/superpowers, vercel-labs/skills, firecrawl/cli, **caveman** |

Economia de tokens + roteamento de modelos: [`model-routing.md`](model-routing.md).

- **OpenWolf no projeto:** `Install-Tools` → `openwolf init`
- **Graphify:** CLI via `uv tool install graphifyy` (global-tools + Install-Tools se ausente); depois `graphify install` (skills do usuario) e `graphify install --project`

## Comandos

```bash
# No init/update (padrao)
orchestrator init
orchestrator update

# So as ferramentas globais
orchestrator global-tools

# Pular globais
orchestrator init --skip-global-tools
```

Relatório (sem segredos): `.orchestrator/tools/global-status.json`

## Escopo

| Camada | Onde |
|---|---|
| Global | `~/.claude`, `~/.cursor/mcp.json`, `~/.agents/skills`, npm global |
| Workspace | `.orchestrator/mcp/registry.json` (espelho dos MCPs recomendados) |

Credenciais (Atlassian, TestSprite, Google Ads, etc.) **não** são gravadas pelo instalador. Plugins que exigem login (ex.: Atlassian) pedem autenticação no próprio cliente.

## Codex

Plugins oficiais (context7, playwright, superpowers, …) já costumam viver em `~/.codex/config.toml`. O instalador não reescreve esse TOML automaticamente para evitar conflitos; use os plugins Codex já habilitados ou o marketplace oficial.
