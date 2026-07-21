# Reference analysis (candidatos)

| Item | Classificação | Evidência |
|---|---|---|
| `docs/legacy/prompt_ambiente_multiagente.md` | legacy_removable → archive | Só docs; deprecado; não usado por instalador |
| `docs/superpowers/**` | legacy_removable → archive | Planos já implementados; refs só internas |
| `scripts/Backup-Orchestrator.ps1` | active (manual) | Nunca chamado pelo pipeline; usa `New-BackupBundle`; utilitário keep |
| `runtime/.../routing/registry.py` | legacy_removable | Zero imports; stub enganoso |
| Stub import `redact` em `mcp/resources.py` | dead | Import não usado |
| Caveman obrigatório em docs/rules | outdated docs | Policy `caveman_enabled: false` |
| Cursor `ide-hint` em docs | outdated docs | Profile é `ide-client` |
| `.superpowers/` local | runtime/user | Não versionado; gitignore |
| OpenWolf/Graphify | experimental opt-in | Keep; init default false |
| `dispatch` | legacy_required | Compat pública |
| Migrations 0.1→0.2→0.3 | active | Keep |
| Skills workspace | active (orientação) | Keep; atualizar textos |
| Adapters CLI | active | Keep |
