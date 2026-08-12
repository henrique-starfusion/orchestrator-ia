# Baseline F0 — estado do orquestrador antes da Plataforma (épico #13)

> Issue: [#14](https://github.com/henrique-starfusion/orchestrator-ia/issues/14) ·
> Épico: [#13](https://github.com/henrique-starfusion/orchestrator-ia/issues/13) ·
> Plano: `.claude/plans/vscode-orchestrator-extension-architecture-plan.md`
>
> Registrado em **2026-08-12**, na versão **0.4.84**, `code_fingerprint`
> `b580eee754299b2f`, a partir de `develop` em `cc7f12e`.

Este documento existe para que toda fase seguinte do épico tenha contra o que
comparar. **Nenhum número aqui foi estimado**: cada valor vem de uma execução
real feita nesta máquina, e a saída está colada abaixo. Onde uma medição diverge
do que o plano registrou, a divergência está marcada explicitamente.

---

## 1. Método

| Fato | Como foi obtido |
|---|---|
| Contagem de testes Python | `python -m pytest runtime/tests -q` executado até o fim |
| Contagem de testes do pacote | `npm test` executado até o fim |
| Versão e fingerprint | `orchestrator version --json` |
| Roteamento de cada comando | leitura de `bin/orchestrator.js` (`mapCommand`, `parseArgs`, `runInstaller`) |
| Destino real dos comandos de instalador | leitura de `scripts/Install-Orchestrator.ps1` |
| Comportamento de `--help` | execução de `orchestrator <cmd> --help` para cada comando |

---

## 2. Arquitetura atual

### 2.1 Camadas

```
CLI do usuário  →  bin/orchestrator.js  →  ┬→ PowerShell (instalador)
                                           └→ python -m orchestrator_runtime (engine)
```

`bin/orchestrator.js` (454 linhas) é o único ponto de entrada real e o **ponto de
compatibilidade permanente** do produto. Ele decide, por comando, se despacha
para o instalador PowerShell ou para o runtime Python.

### 2.2 Entrypoints

| Arquivo | Papel |
|---|---|
| `bin/orchestrator.js` | wrapper Node; roteia todo comando |
| `orchestrator-ia.bat` | atalho Windows |
| `install.ps1`, `get.ps1` | bootstrap de instalação |
| `scripts/Install-Orchestrator.ps1` | **front controller** de todos os comandos de instalador |
| `runtime/src/orchestrator_runtime/__main__.py` | entrada do engine Python |

### 2.3 Módulos do runtime

`runtime/src/orchestrator_runtime/`:

| Módulo | Conteúdo |
|---|---|
| `tasks/` | `models.py`, `repository.py`, `service.py`, `state_machine.py` |
| `planning/`, `routing/`, `execution/`, `validation/` | ciclo do laço |
| `agents/` | adapters dos CLIs de agente |
| `memory/` | `database.py`, `episodes.py`, `learnings.py`, `performance.py`, `retrieval.py`, `strategies.py` |
| `mcp/` | servidor MCP (front controller para Cursor/Claude) |
| `testing/`, `diagnostics/`, `documentation/`, `rules/`, `skills/` | apoio |
| `events.py` | `EventType` + `RuntimeEvent` |
| `cli.py`, `config.py`, `callers.py`, `watch.py`, `errors.py`, `textutil.py` | superfície e utilidades |

**Confirmado para a Fase 2:** `RuntimeEvent` é `BaseModel` em
`runtime/src/orchestrator_runtime/events.py:46`, com os campos `task_id`,
`timestamp`, `type`, `role`, `agent`, `data` — a fonte canônica Pydantic que o
protocolo vai derivar existe e está onde o plano diz.

### 2.4 Configuração canônica

`.orchestrator/` — **contrato com a frota, não tocar** (seção 8.3 do plano):

```
agents/  config/  data/  hooks/  mcp/  memory/  orchestration/
rules/  runtime/  schemas/  scripts/  skills/  tools/  README.md  VERSION
```

`.orchestrator/config/`: `models.json`, `manager_model.json`, `orchestrator.json`,
`policies.json`, `routing.json`, `tools.json`, `validation.json`.

### 2.5 Instalador

38 scripts em `scripts/`. Todos os comandos de instalador entram por
`Install-Orchestrator.ps1`, que delega aos irmãos — `Update-Orchestrator.ps1`,
`Validate-Orchestrator.ps1`, `Repair-Orchestrator.ps1`,
`Uninstall-Orchestrator.ps1`, entre outros.

### 2.6 Suítes

- `runtime/tests/` — `unit/`, `integration/`, `conftest.py` (Python)
- `tests/` — suíte PowerShell do pacote, executada por `npm test`

---

## 3. Baseline de testes — saídas reais

### 3.1 `python -m pytest runtime/tests -q`

```
766 passed, 3 skipped, 4 warnings in 148.03s (0:02:28)
```

> **Divergência com o plano.** A seção 3 do plano e a issue #14 registram
> `749 passed / 3 skipped`. O valor real hoje é **766 passed / 3 skipped**.
> O número do plano está defasado; o baseline válido é o desta execução.

**Duas armadilhas de reprodução, ambas observadas ao medir:**

1. **Raiz de temp compartilhada.** Rodar dois pytest ao mesmo tempo na mesma
   máquina faz o teardown quebrar com
   `PermissionError: [WinError 5] Acesso negado: '...\pytest-of-henrique\pytest-current'`.
   Os testes passam; só a limpeza falha, e o processo sai com código 1. Para
   medir em paralelo, use `PYTEST_DEBUG_TEMPROOT` exclusivo.
2. **`MAX_PATH` do Windows.** Se o `PYTEST_DEBUG_TEMPROOT` apontar para um
   caminho longo, **17 testes falham e 3 dão erro** — `test_0461_worktrees.py`,
   `test_0461_fanout_service.py`, `test_git_changed_files.py`,
   `test_0435_guardline_fixes.py`. A causa é `git worktree add` estourando o
   limite de caminho, não regressão de código: `create_worktree` cria a worktree
   **dentro** do projeto sob teste, e o projeto sob teste vive na raiz de temp.
   Use uma raiz curta (ex.: `C:/Users/<user>/pt0`).

### 3.2 `npm test`

```
Total: 34 | Passed: 34 | Failed: 0
```

> **Divergência com o plano.** Plano e issue registram `32/32`. O real é
> **34/34** — a suíte cresceu (inclui `Test-WikiPublishing`, da issue #9).

### 3.3 `orchestrator version --json`

```json
{
  "version": "0.4.84",
  "code_fingerprint": "b580eee754299b2f"
}
```

O `code_fingerprint` é o mecanismo que detecta MCP obsoleto; clientes MCP em
Cursor e Claude dependem dele.

### 3.4 `orchestrator status`

```
=== Orchestrator Status ===
Project:           D:\StarFusion\bootstrap-agents
Package version:   0.4.84
Workspace version: 0.4.84
Agents available:  5
  - claude (unknown)
  - codex (npm)
  - kimi (unknown)
  - opencode (chocolatey)
  - cursor (unknown)
Tools registered:  2
```

---

## 4. Tabela de compatibilidade

Roteamento **verificado no código**, não presumido. `mapCommand`
(`bin/orchestrator.js:94`) normaliza aliases: `init`/`i` → `install`,
`upgrade` → `update`, e argv vazio → `install`.

| Comando | Roteado para | Destino concreto | `--help` próprio? |
|---|---|---|---|
| `init` | PowerShell | `Install-Orchestrator.ps1 install` (alias) | **Não** |
| `install` | PowerShell | `Install-Orchestrator.ps1 install` | **Não** |
| `update` / `upgrade` | PowerShell | `Install-Orchestrator.ps1 update` → `Update-Orchestrator.ps1` | **Não** |
| `verify` | PowerShell | `Install-Orchestrator.ps1 verify` → `Validate-Orchestrator.ps1` | **Não** |
| `repair` | PowerShell | → `Repair-Orchestrator.ps1` | **Não** |
| `uninstall` | PowerShell | → `Uninstall-Orchestrator.ps1` | **Não** |
| `status` | PowerShell | `Install-Orchestrator.ps1 status` | **Não** |
| `analyze`, `skills`, `global-tools`, `route`, `dispatch`, `legacy` | PowerShell | `Install-Orchestrator.ps1 <cmd>` | **Não** |
| `run` | Python | `python -m orchestrator_runtime run` | **Sim** |
| `task <sub>` | Python | `python -m orchestrator_runtime task` | **Sim** |
| `mcp serve` | Python | `python -m orchestrator_runtime mcp` | **Sim** |
| `cursor`, `agents`, `tools` | Python | `python -m orchestrator_runtime <cmd>` | **Sim** |
| `version` | nenhum | resolvido no próprio JS | — |

> **Correção ao plano.** A seção 3 do plano diz que `update` vai para
> `scripts/Update-Orchestrator.ps1` e `verify` para `Validate-Orchestrator.ps1`.
> O wrapper Node **nunca** chama esses scripts diretamente: ele só conhece
> `Install-Orchestrator.ps1` (`bin/orchestrator.js:16`), que age como front
> controller e delega aos irmãos. Isso *reduz* o risco da Fase 6 — há um único
> caminho de script a preservar, não nove.

### 4.1 Comportamento de `--help` — assimetria confirmada

Comando de instalador **não tem ajuda própria**. `parseArgs` intercepta `-h`
e `--help` (`bin/orchestrator.js:182`) antes de chegar ao PowerShell e imprime
o banner genérico. Verificado executando: `init`, `install`, `update`, `verify`,
`status` e `dispatch` com `--help` produzem **saída idêntica** — o banner.

Comando de runtime passa os argumentos adiante (`bin/orchestrator.js:163`) e o
Typer responde com a ajuda real. Exemplo, `orchestrator run --help`:

```
 Usage: python -m orchestrator_runtime run [OPTIONS]

 *  --prompt          <str>   Atividade a executar [required]
    --project         <path>  Caminho do projeto
    --profile         <str>   [default: balanced]
    --max-iterations  <int>
    --timeout         <int>
    --planner / --executor / --validator / --manager-provider  <str>
    --loop            <str>   Loop de execucao (bug|mvp|landing|conteudo|saas)
    --scope           <str>   Caminho que esta task pode tocar (repetivel)
    --fake-agents             Adapters falsos (CI)
    --json / --dry-run / --verbose|--quiet
```

`orchestrator task --help` lista os subcomandos:
`create`, `run`, `status`, `list`, `cancel`, `resume`, `logs`, `watch`, `artifacts`.

---

## 5. Consumidores externos que não podem quebrar

1. **Doze projetos da frota** com `.orchestrator/` instalado, atualizados por
   propagação de `orchestrator update`. Dois versionam `.orchestrator/` no
   próprio git.
2. **Clientes MCP** em Cursor e Claude, que usam `code_fingerprint` para
   detectar runtime obsoleto.
3. **Regras dos seis adaptadores** (`CLAUDE.md`, `AGENTS.md`, `CURSOR.md`,
   `GEMINI.md`, `KIMI.md`, e o pacote de skills), que instruem agentes a chamar
   `orchestrator run` e `orchestrator task watch` com essa grafia exata.

---

## 6. Riscos de migração, por comando

| Comando | Risco | Por quê, concretamente |
|---|---|---|
| `update` | **Alto** | Propaga para 12+ projetos. Um erro sai da máquina e entra na frota; rollback exige propagar de novo. |
| `run` | **Alto** | Caminho crítico do produto e o que os seis adaptadores mandam usar. Assinatura e nome dos flags são contrato de fato. |
| `mcp serve` | **Alto** | Clientes MCP já configurados apontam para ele. Mudar transporte ou nome deixa Cursor e Claude mudos, sem erro visível ao usuário. |
| `task <sub>` | **Médio** | `watch`, `status` e `resume` estão escritos nas regras dos agentes; `watch` é o canal oficial de acompanhamento. |
| `install` / `init` | **Médio** | Caminho de `Install-Orchestrator.ps1` está fixado em `bin/orchestrator.js:16`. Mover `scripts/` sem atualizar essa constante quebra **todo** comando de instalador de uma vez. |
| `verify` | **Médio** | É o gate que a frota usa para saber se a instalação está sã; falso verde é pior que falha. |
| `status` | **Baixo** | Só leitura. |
| `dispatch`, `route` | **Baixo** | Despacho único, sem estado persistido. |
| `legacy <ação>`, `skills`, `global-tools` | **Baixo** | Fluxos isolados, sem consumidor externo. |

### 6.1 Riscos transversais, observados nesta medição

1. **Ponto único de falha no roteamento.** `bin/orchestrator.js:16` guarda o
   caminho de `Install-Orchestrator.ps1` numa constante. É o arquivo mais
   sensível de todo o épico: encapsular `scripts/` como `installer/` na Fase 6
   sem tocar nessa linha derruba os 12 comandos de instalador juntos.
2. **`--help` de instalador não é ajuda, é banner.** Qualquer teste de fase que
   use `orchestrator <cmd> --help` como prova de que o comando sobreviveu vai
   dar **falso verde**. Verificado: `orchestrator comando-que-nao-existe --help`
   imprime o mesmo banner e **sai com código 0**. O gate por comando precisa
   exercer comportamento real, não `--help`.
3. **Suíte sensível a `MAX_PATH`.** As worktrees nascem dentro do projeto sob
   teste (`create_worktree`, por exigência de `assert_within_project`). Como a
   Fase 6 move diretórios e a Fase 4 acrescenta o daemon multi-workspace, o
   comprimento de caminho tende a crescer — e o modo de falha é um bloco de 20
   testes que parece regressão de lógica sem ser.
4. **Baselines do plano estão defasados.** Duas das três contagens da seção 3 do
   plano estavam erradas na data de hoje (749 vs 766, 32 vs 34). Fases seguintes
   devem comparar contra **este** documento, não contra o plano.

---

## 7. Aceitação da F0

- [x] Documento de baseline com as saídas reais coladas
- [x] Nenhum arquivo de código alterado — o diff da F0 é só `docs/`
- [x] Riscos de migração listados por comando
