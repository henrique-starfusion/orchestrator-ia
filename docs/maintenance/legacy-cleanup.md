# Limpeza de legado (manutenção)

Resumo operacional da limpeza **0.3.1**. Detalhe auditável em [`docs/cleanup/`](../cleanup/).

## Arquitetura canônica

```text
Cursor (MCP front controller) → Runtime → Manager → CLI agents → testes → validação → docs → memória
Fonte: .orchestrator/
```

## O que foi arquivado

- Prompts bootstrap → `docs/archive/prompts/`
- Specs/planos Superpowers → `docs/archive/superpowers/`

## Anti-regressão

`tests/Test-NoLegacyArtifacts.ps1` (incluído em `npm test` via `Run-AllTests.ps1`):

- template sem `.claude`/`.ai` como fonte canônica
- prompt legado só em archive
- Cursor `ide-client` / não executável
- InitTools / GlobalTools opt-in
- sources do manifest existentes
- sem `docs/superpowers/` ativo

## Não remover sem análise

Migrations, adapters públicos, `dispatch`, catálogo OpenWolf/Graphify/Caveman (opt-in), `Backup-Orchestrator.ps1`.
