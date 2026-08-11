# Testes

O repositório tem **duas suítes independentes**, declaradas em
`package.json:38-42`:

| Script | Comando | Cobre |
|---|---|---|
| `npm test` | `powershell -NoProfile -ExecutionPolicy Bypass -File tests/Run-AllTests.ps1` | Instalador, adaptadores, detecção de agentes, hooks, legacy |
| `npm run test:runtime` | `python -m pytest -q runtime/tests` | Runtime Python |
| `npm run test:all` | os dois em sequência | Tudo |

Nota importante para agentes e automação: a descoberta de testes do próprio
runtime, aplicada a este repositório, acha `package.json` e propõe `npm test`
(`testing/discovery.py:63-66`) — ou seja, a suíte PowerShell. A suíte Python
precisa ser chamada explicitamente.

## Suíte do runtime (pytest)

Configuração em `runtime/pyproject.toml`, seção `tool.pytest.ini_options`:
`asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["src"]`.
Dependências de desenvolvimento: `pytest>=8.0` e `pytest-asyncio>=0.23`.

Estrutura:

```text
runtime/tests/
  conftest.py                       fixtures compartilhadas
  unit/                             68 arquivos de teste
  integration/test_end_to_end_fake_agents.py
```

### O que o conftest garante

- **Isolamento da flag de filho**: fixture autouse remove
  `ORCHESTRATOR_CHILD_AGENT` do ambiente (`runtime/tests/conftest.py:11-17`).
  Sem isso, a suíte rodando dentro de um dispatch herda a marca e o guard
  anti-recursão derruba os testes.
- **Fixture `project`**: monta um `.orchestrator/` completo em `tmp_path`, com
  `config/policies.json`, `config/models.json`, `agents/profiles/`,
  `runtime/locks/`, `data/` e `memory/` (`conftest.py:20` em diante). O
  `policies.json` da fixture desliga `caveman_enabled`, para os prompts de teste
  ficarem previsíveis.

### Grupos de teste

Os arquivos em `runtime/tests/unit/` seguem duas convenções de nome.

**Por área funcional** (o que cada componente faz):

| Arquivo | Cobre |
|---|---|
| `test_agent_registry.py` | Registro, capacidades e ordem de preferência de agentes |
| `test_agent_process.py` | `CliExecutor`: spawn, timeout, redação, kill |
| `test_agent_timeout_budget.py`, `test_agent_timeout_issue.py` | Orçamento de tempo por papel e a issue de timeout |
| `test_codex_infra_failfast.py` | Fail-fast dos marcadores de infra do sandbox Windows |
| `test_cli.py`, `test_cli_encoding.py` | CLI Typer e contrato de encoding UTF-8 |
| `test_completion_gate.py` | Portão final de conclusão |
| `test_criteria_builder.py` | Precedência entre ACs declarados, do loop e heurísticos |
| `test_correction_loop.py` | Ciclo executar-validar-corrigir |
| `test_context_compaction.py` | Learn-then-compact e o digest |
| `test_diagnostics.py` | Fingerprint de código e lista de features |
| `test_documentation_gate.py` | Gate documental e validação de links |
| `test_git_changed_files.py` | Baseline git, hashes seletivos em árvore suja, repos aninhados e enriquecimento de arquivos alterados |
| `test_global_tooling_always_on.py` | Bloco de ferramentas obrigatórias no prompt |
| `test_locks.py` | `WriteLock`, reentrância e reivindicação de lock órfão |
| `test_mcp_tools.py`, `test_mcp_tool_docstrings.py` | Tools MCP e o texto que orienta o agente de chat |
| `test_memory.py` | Persistência e busca de memórias |

**Por versão de correção** (regressão de um defeito específico): arquivos com
prefixo numérico, de `test_0416_fixes.py` a `test_0461_worktrees.py`. Cada um
fixa o comportamento que uma release corrigiu — por exemplo
`test_0426_cancel_stops_loop_e2e.py` (cancel realmente para o loop),
`test_0441_child_flag.py` (flag de filho por valor, não por presença),
`test_0444_test_baseline.py` (falha pré-existente não é cobrada da task),
`test_0447_agent_quarantine.py` (quarentena de agente com serviço morto),
`test_0453_premise_mismatch.py` (premissa falsa é resultado de primeira classe)
e `test_0461_fanout_split.py` (decomposição com escopos disjuntos).

Essa convenção é deliberada: cada defeito corrigido deixa um teste com o número
da versão, o que torna trivial ligar um comportamento estranho à release que o
introduziu ou consertou.

### Teste de integração

`runtime/tests/integration/test_end_to_end_fake_agents.py` roda o ciclo
completo com adapters falsos (`FakeAgentAdapter`,
`agents/base_adapters.py:236`), ligados por `fake_agents=True`
(`agents/__init__.py:82-86`). O adapter falso escreve um módulo `soma` com
teste e README (`_write_soma_module`, `agents/base_adapters.py:296`) e devolve
um veredito `approved` com score 0.95 quando age como validator. É assim que o
pipeline inteiro — estados, testes, validação, gate documental — é exercitado
sem depender de nenhum CLI instalado.

## Suíte PowerShell (instalador)

Orquestrada por `tests/Run-AllTests.ps1`: descobre todo `Test-*.ps1` do
diretório, exceto `Test-Helpers.ps1`, roda cada um em processo separado com
`-NoProfile -ExecutionPolicy Bypass` e agrega PASS/FAIL numa tabela final
(`tests/Run-AllTests.ps1:11-57`). Sai com código 1 se qualquer teste falhar.

Assim como o pytest, o runner **limpa `ORCHESTRATOR_CHILD_AGENT`** antes de
começar (`tests/Run-AllTests.ps1:5-9`), porque a suíte pode estar rodando sob o
próprio orquestrador em VALIDATING.

Os 33 arquivos se agrupam assim:

| Grupo | Arquivos | Cobre |
|---|---|---|
| Instalação e ciclo de vida | `Test-Install.ps1`, `Test-Upgrade.ps1`, `Test-Repair.ps1`, `Test-Uninstall.ps1`, `Test-Idempotency.ps1` | Instalar, atualizar, reparar, remover, e rodar duas vezes sem efeito colateral |
| Adaptadores | `Test-Adapters.ps1`, `Test-CurrentAdaptersPreserved.ps1`, `Test-MergeAdditive.ps1` | Geração dos adaptadores por vendor e preservação do que o usuário já tinha |
| Agentes | `Test-AgentDetection.ps1`, `Test-AgentProfiles.ps1`, `Test-AgentUpdates.ps1`, `Test-IdeAgentDetection.ps1`, `Test-DefaultAgent.ps1` | Detecção no PATH, forma dos profiles, atualização dos CLIs |
| Hooks | `Test-Hooks.ps1`, `Test-GraphifyHookRepair.ps1` | Instalação e reparo dos hooks |
| Roteamento e despacho | `Test-ModelRouting.ps1`, `Test-DispatchMonitoring.ps1`, `Test-CursorDefaultOrchestration.ps1` | Resolução de rota por classe de tarefa e comportamento padrão no Cursor |
| Legacy | `Test-LegacyDetection.ps1`, `Test-LegacyBackup.ps1`, `Test-LegacyMigration.ps1`, `Test-LegacyRestore.ps1`, `Test-LegacyCleanupSafe.ps1`, `Test-LegacyCleanupAggressive.ps1`, `Test-LegacyCleanupReportOnly.ps1`, `Test-LegacyCleanupIdempotency.ps1`, `Test-LegacyUnknownPreservation.ps1`, `Test-LegacyUserOwnedPreservation.ps1`, `Test-NoLegacyArtifacts.ps1` | Todo o pipeline de configuração legada: detectar, fazer backup, migrar, remover nos três modos, restaurar, e nunca apagar o que é do usuário |
| Propagação | `Test-ProjectPropagate.ps1` | Update do pacote chegando aos projetos registrados |
| Pacote Git | `Test-PackageSyncHistory.ps1` | Clone completo preservado, merge ff-only, caminho shallow e clone novo com profundidade 1 |

`Test-Helpers.ps1` é biblioteca, não teste — está explicitamente excluída da
descoberta. Fixtures ficam em `tests/fixtures/`.

## Como rodar

```bash
npm test                 # suíte PowerShell (instalador)
npm run test:runtime     # suíte pytest (runtime)
npm run test:all         # as duas
```

Um teste isolado do runtime:

```bash
python -m pytest -q runtime/tests/unit/test_locks.py
python -m pytest -q runtime/tests -k quarantine
```

Um teste isolado do instalador:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tests/Test-Install.ps1
```

### Armadilha conhecida do basetemp

Não use a variável `PYTEST_ADDOPTS` com `--basetemp` ao validar este runtime:
workflows falsos executam `pytest -q` como processo filho e herdam a opção.
Passe `--basetemp` apenas na linha de comando externa
(`npm run test:runtime -- --basetemp ...`). Registro do aprendizado em
`.wolf/cerebrum.md`, seção Do-Not-Repeat.

### Ambiente

O runtime valida o próprio ambiente com `orchestrator version --json`, que
devolve `code_fingerprint` e a lista de `features`
(`cli.py:64-83`, `diagnostics.py`). Fingerprint diferente entre o CLI e o
servidor MCP significa MCP rodando código velho — recarregue o cliente antes de
investigar comportamento estranho.
