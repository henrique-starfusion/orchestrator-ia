# Migrações de versão

Scripts de migração incrementais entre versões do Orquestrador IA Multiagente.

## Convenção de nomenclatura

```text
<from>-to-<to>.ps1
```

Exemplos:

```text
0.1.0-to-0.2.0.ps1
0.2.0-to-0.3.0.ps1
```

- `<from>` e `<to>` seguem semver (`MAJOR.MINOR.PATCH`).
- Cada script aplica **somente** as mudanças necessárias para ir de `<from>` para `<to>`.
- Migrações nunca reconstruem `.orchestrator/` do zero.

## Execução

O comando `upgrade` detecta scripts em `package/migrations/` e registra aviso quando presentes. A aplicação automática completa será evoluída em versões futuras; até lá, revise e execute manualmente quando necessário.

## Escopo permitido

- Criar ou atualizar arquivos definidos pelo manifest.
- Mover conteúdo legado para caminhos canônicos.
- Ajustar registros JSON (`agents`, `skills`, `mcp`, etc.).

## Escopo proibido

- Apagar ou esvaziar `.orchestrator/` inteiro.
- Sobrescrever conteúdo `user-owned` sem confirmação explícita.
- Executar testes ou scripts de um produto específico embutidos no pacote.
