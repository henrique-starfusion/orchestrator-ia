# Documentation policy

**Hard rule:** toda tarefa avalia impacto documental antes da conclusão.

## Fonte da verdade e Wiki

`docs/` neste repositório é a fonte da verdade da documentação. A Wiki do
GitHub é uma publicação **derivada**: cada arquivo Markdown de `docs/` gera uma
página, e `docs/README.md` também serve de base para a página `Home` e seu
índice completo.

Edição manual feita diretamente na Wiki não é fonte autoritativa e será
sobrescrita pela próxima sincronização. A mudança durável deve ser feita em
`docs/` e revisada no repositório de código.

### Sincronização atual, sem GitHub Actions

Execute na raiz do repositório:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Publish-Wiki.ps1
```

O publicador clona a Wiki em diretório temporário, converte links, gera as
páginas e faz commit/push na Wiki somente quando existe mudança real.

### Sincronização futura, com GitHub Actions

O workflow está preservado e desabilitado em
[`../.github/wiki-sync.yml.disabled`](../.github/wiki-sync.yml.disabled). Quando
a conta voltar a ter plano/limite de Actions, siga
[`../.github/ACTIONS.md`](../.github/ACTIONS.md) para movê-lo para
`.github/workflows/wiki-sync.yml` e execute o disparo manual inicial. Depois de
ativado, pushes que alterem `docs/**` ou o publicador voltam a sincronizar a
Wiki automaticamente.

Estado: `UPDATING_DOCUMENTATION`.

Registro mínimo:

```json
{
  "required": true,
  "reason": "",
  "files_updated": [],
  "files_reviewed": [],
  "validation": "passed"
}
```

Sem esse registro, a tarefa não pode ser `COMPLETED`.

Mensagem padrão (policies/skills/adapters):

> Ao final de cada tarefa, revisar e atualizar a documentação afetada antes da conclusão.
