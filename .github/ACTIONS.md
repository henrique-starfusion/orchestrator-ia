# GitHub Actions (desabilitado)

O workflow de CI foi desabilitado porque a conta nao tem plano/limite de
Actions disponivel (billing/spending limit).

Arquivos preservados (nao executados pelo GitHub):

- [`ci.yml.disabled`](ci.yml.disabled) — antigo `.github/workflows/ci.yml`
- [`wiki-sync.yml.disabled`](wiki-sync.yml.disabled) — republica a Wiki a
  partir da fonte da verdade em `docs/`

Enquanto Actions estiver indisponivel, a sincronizacao da Wiki e manual:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Publish-Wiki.ps1
```

O script clona a Wiki em diretorio temporario, gera todas as paginas, cria
commit e faz push somente quando existe mudanca real.

Para reativar quando houver plano:

1. Crie `.github/workflows/`.
2. Mova `ci.yml.disabled` para `workflows/ci.yml` se quiser reativar o CI.
3. Mova `wiki-sync.yml.disabled` para `workflows/wiki-sync.yml` para reativar a
   publicacao da Wiki.
4. Confirme que o workflow tem permissao `contents: write` e execute
   `workflow_dispatch` uma vez.
5. Commit e push.

Nao mova os arquivos enquanto a conta estiver sem plano/limite: permanecer fora
de `.github/workflows/` e o mecanismo que garante que nenhum workflow rode.

Testes locais continuam sendo a fonte de verdade:

```bash
cd runtime && python -m pytest -q
./tests/Run-AllTests.ps1
```

> Este arquivo e `.github/ACTIONS.md` (nao `README.md`). O GitHub prioriza
> `.github/README.md` sobre o README da raiz — por isso o texto de Actions
> nao pode viver como README aqui.
