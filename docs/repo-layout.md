# Layout deste repositório

Este repositório é **ao mesmo tempo**:

1. o **pacote de distribuição** `@starfusion/orchestrator`;
2. um **workspace dogfood** (instalação local em `.orchestrator/`, ignorada pelo git).

## Branches Git

| Branch | Papel |
|---|---|
| `main` | Produção / releases estáveis |
| `develop` | Desenvolvimento ativo (trabalho padrão) |

Instalação via npm/GitHub deve apontar para `#develop` (ou tag de release em `main`).

## Raiz (entrada e metadados)

| Item | Papel |
|---|---|
| `bootstrap-agents.bat` | Wrapper Windows fino → `scripts/Install-Orchestrator.ps1` (**em uso**) |
| `install.ps1` | Atalho PowerShell local (**em uso**) |
| `get.ps1` | One-liner / cache + install (**em uso**) |
| `bin/orchestrator.js` | CLI npm `orchestrator` / `mao` (**em uso**) |
| `package.json` | Pacote npm |
| `VERSION` / `LICENSE` / `README.md` | Metadados do produto |

## Pacote

| Pasta | Papel |
|---|---|
| `package/template/.orchestrator/` | Template canônico versionado |
| `package/template/adapters/` | Adaptadores por vendor |
| `package/global-tools/catalog.json` | Catálogo de MCPs/plugins/skills globais |
| `package/manifest.json` | Arquivos gerenciados |
| `package/checksums.json` | Integridade |
| `package/migrations/` | Migrations de versão |
| `runtime/` | Runtime Python multiagente (SQLite) |

Documentação completa: [`orquestrador.md`](orquestrador.md) · [`runtime-architecture.md`](runtime-architecture.md) · [`mcp-integration.md`](mcp-integration.md).

## Runtime do instalador

| Pasta | Papel |
|---|---|
| `scripts/` | Lógica PowerShell (install/update/verify/…) |
| `tests/` | Testes do instalador em fixtures temporárias |
| `runtime/tests/` | Testes do runtime (pytest) |
| `docs/` | Documentação do produto |
| `docs/legacy/` | Material deprecado (não usar no fluxo atual) |
| `.cursor/rules/` | Regras Cursor versionadas deste pacote |

## Gerado no workspace (gitignored)

| Item | Papel |
|---|---|
| `.orchestrator/` | Instalação dogfood deste repo |
| `.wolf/` | OpenWolf (se init tools) |
| `CLAUDE.md`, `AGENTS.md`, `.claude/`, … | Adaptadores gerados |

## O que NÃO usar

- `docs/legacy/prompt_ambiente_multiagente.md` — prompt antigo baseado em `.claude/`
