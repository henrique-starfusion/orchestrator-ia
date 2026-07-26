# Design — Propagar update do pacote para projetos registrados (0.4.20)

## Decisões

- Registro + `--discover` opcional (opção C)
- Propagação **somente** quando o update é do próprio pacote (`ProjectPath == PackageRoot`)
- `--propagate` default ON; `--no-propagate` opt-out; `--discover` opt-in

## Registro

Path: `%LOCALAPPDATA%\StarFusion\orchestrator\projects.json`

```json
{
  "projects": [
    { "path": "D:\\StarFusion\\printbee", "last_seen": "ISO", "version": "0.4.19" }
  ],
  "discover_roots": ["D:\\StarFusion"]
}
```

Upsert em todo `install`/`update` bem-sucedido (projeto com `.orchestrator/`).

## Propagação

Após update bem-sucedido do pacote:

1. (Opcional) `--discover`: varrer `discover_roots` + pai do PackageRoot por `.orchestrator/VERSION`
2. Para cada path registrado válido (existe, tem VERSION, versão &lt; pacote):
   invocar update com `-SkipAgentUpdates` (Update-Agents já rodou no pacote)
3. Relatório: path | from→to | OK|SKIP|ERRO

## Critérios

- AC1: install/update registra o projeto
- AC2: update no PackageRoot propaga para registrados atrás
- AC3: update só no PrintBee **não** propaga
- AC4: `--no-propagate` desliga; `--discover` acha projetos não registrados
- AC5: testes + docs + VERSION 0.4.20
