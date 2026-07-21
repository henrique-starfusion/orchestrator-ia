# Validation baseline

Pré-limpeza (`1171835`):

- `python -m pytest runtime/tests` → 34 passed
- `npm test` → 14 passed

Pós-limpeza (0.3.1):

- `npm test` → 15/15 (inclui `Test-NoLegacyArtifacts`)
- `npm run test:runtime` → 34 passed
- Sync dogfood: `.orchestrator/agents/profiles/cursor.json` = template `ide-client`
