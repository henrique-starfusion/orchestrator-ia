# Removal plan

| Item | Classificação | Evidência de não uso | Ação | Risco | Validação |
|---|---|---|---|---|---|
| Prompt legado operacional | legacy_removable | Sem refs no instalador/CLI | archive | baixo | Test-NoLegacy + docs links |
| docs/superpowers | legacy_removable | Specs já no código | archive | baixo | Test-NoLegacy |
| routing/registry.py | dead | `rg` sem imports | delete | nenhum | pytest |
| import redact não usado | dead | leitura do arquivo | delete import | nenhum | pytest |
| Docs/rules caveman hard | outdated | policies.json | replace textos | baixo | review + testes |
| Docs cursor ide-hint | outdated | cursor.json | replace | baixo | Test-AgentProfiles |
| .gitignore incompleto | incomplete | lista do prompt | merge | baixo | git check |
| Backup-Orchestrator.ps1 | active manual | wrapper útil | keep + docstring | n/a | — |
| dispatch / migrations | legacy_required | consumidores | keep | — | — |

Não há remoção pública breaking → SemVer **patch** 0.3.1.
