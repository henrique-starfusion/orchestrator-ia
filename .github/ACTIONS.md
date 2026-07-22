# GitHub Actions (desabilitado)

O workflow de CI foi desabilitado porque a conta nao tem plano/limite de
Actions disponivel (billing/spending limit).

Arquivo preservado (nao e executado pelo GitHub):

- [`ci.yml.disabled`](ci.yml.disabled) — antigo `.github/workflows/ci.yml`

Para reativar quando houver plano:

1. Mova `ci.yml.disabled` para `workflows/ci.yml`
2. Commit e push

Testes locais continuam sendo a fonte de verdade:

```bash
cd runtime && python -m pytest -q
./tests/Run-AllTests.ps1
```

> Este arquivo e `.github/ACTIONS.md` (nao `README.md`). O GitHub prioriza
> `.github/README.md` sobre o README da raiz — por isso o texto de Actions
> nao pode viver como README aqui.
