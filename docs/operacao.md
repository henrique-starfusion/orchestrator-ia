# Operação

Comandos verificados contra `bin/orchestrator.js` (roteamento),
`scripts/Install-Orchestrator.ps1` (instalador) e
`runtime/src/orchestrator_runtime/cli.py` (runtime).

## Pré-requisitos

- **Node 18 ou superior** (`package.json:23-25`).
- **Python 3.11 ou superior** (`runtime/pyproject.toml`, `requires-python`).
  O wrapper prefere o venv em `runtime/.venv` antes do PATH
  (`bin/orchestrator.js:296-321`).
- **PowerShell 5.1 ou superior** para o instalador
  (`scripts/Install-Orchestrator.ps1:1`).

## Instalar num projeto

```bash
orchestrator init            # alias de install (bin/orchestrator.js:95)
orchestrator install
```

O que o install faz, além de criar `.orchestrator/`: detecta os CLIs no PATH,
sonda as flags que cada um aceita, gera os adaptadores por vendor, repara hooks
e valida o resultado. A sequência está detalhada em `arquitetura.md`, camada 2.

Opções que mudam o escopo (mapeadas em `bin/orchestrator.js:225-254`):

| Flag | Efeito |
|---|---|
| `--dry-run` | Simula sem escrever |
| `--force` | Sobrescreve arquivos existentes |
| `--skip-agent-updates` | Não atualiza os CLIs de agente |
| `--skip-agent-probes` | Não sonda flags dos CLIs |
| `--init-tools` | Inicializa OpenWolf e Graphify (opt-in) |
| `--global-tools` | Instala MCPs, plugins e skills no perfil do usuário (opt-in) |
| `--configure-cursor-mcp` | Registra o MCP no Cursor |
| `--legacy-cleanup-mode safe\|aggressive\|report-only` | Modo da limpeza de configuração legada |

## Verificar e reparar

```bash
orchestrator verify     # Detect-Environment + Validate-Orchestrator + Validate-Hooks
orchestrator status
orchestrator repair
orchestrator version --json
```

`verify` encadeia três scripts (`Install-Orchestrator.ps1:229-249`). O
`version --json` delega o fingerprint ao runtime Python
(`bin/orchestrator.js:65-91`) e devolve `version`, `code_fingerprint`,
`features`, `module_path` e `package_root` (`cli.py:64-83`) — é a forma de
detectar um servidor MCP rodando código velho.

## Atualizar

```bash
orchestrator update              # no projeto
orchestrator update --force
orchestrator update --no-propagate
orchestrator update --discover
```

Rodando no workspace do **pacote**, o update propaga para os projetos
registrados (`Propagate-OrchestratorUpdate.ps1`). Opt-out: `--no-propagate`.
Com `--discover`, o script varre as raízes de descoberta em busca de
diretórios com `.orchestrator/` e os registra antes de propagar
(`Propagate-OrchestratorUpdate.ps1:34-51`).

O registro da frota fica em
`%LOCALAPPDATA%\StarFusion\orchestrator\projects.json`
(`Orchestrator.Common.ps1:1088-1094`), com override pela variável
`ORCHESTRATOR_PROJECTS_REGISTRY`. Fixtures mortas em `Temp` são podadas antes
da propagação (`Prune-OrchestratorProjectRegistry`,
`Propagate-OrchestratorUpdate.ps1:31`).

## Rodar uma task

```bash
orchestrator run --prompt "<atividade com critérios de aceitação>"
orchestrator run --prompt "..." --executor claude --validator claude
orchestrator run --prompt "..." --loop bug
orchestrator run --prompt "..." --dry-run
```

Opções reais do comando `run` (`cli.py:114-166`): `--project`, `--profile`,
`--max-iterations`, `--timeout`, `--planner`, `--executor`, `--validator`,
`--manager-provider`, `--loop`, `--fake-agents`, `--json`, `--dry-run`,
`--verbose/--quiet`.

`--loop` aceita o id com ou sem o prefixo `loop-` e falha com exit 2 se o loop
não existir (`cli.py:133-143`). Loops registrados em `planning/loops.py:68`:
`bug`, `ui-probe`, `review`, `mvp`, `landing`, `conteudo`, `saas`, `research`.

O comando sai com código 0 só quando a task termina `COMPLETED`
(`cli.py:166`).

Em Windows, o validador **codex** é problemático em sandbox; o próprio profile
documenta o override automático para `danger-full-access`
(`.orchestrator/agents/profiles/codex.json`, campo `notes`).

## Acompanhar uma task

```bash
orchestrator task list                 # id, estado e prévia do prompt
orchestrator task status <task_id>     # JSON com estado, iteração, score, plano
orchestrator task logs <task_id>       # todos os eventos persistidos
orchestrator task artifacts <task_id>  # saídas gravadas em disco
```

Subcomandos existentes: `create`, `run`, `status`, `list`, `cancel`, `resume`,
`logs`, `artifacts` (`cli.py:169-293`).

`task status` devolve `id`, `status`, `iteration`, `last_score`, `plan`,
`error` e `documentation_review`; para task em `QUEUED`, acrescenta
`queue_position` e `blocked_by` (`tasks/service.py:453-473`).

Efeito colateral útil: tanto `status` quanto `list` disparam a varredura de
zumbis e a adoção de órfã (`tasks/service.py:366-369` e `456-460`). Fazer poll
é, em si, parte da manutenção.

Pelo MCP, o par equivalente é `orchestrator_status` e `orchestrator_events`. A
resposta de status traz `next_poll_after_seconds` (`mcp/tools.py:623`), papel e
modelo ativos, e uma lista dos últimos doze eventos resumidos
(`mcp/tools.py:631-700`).

## Cancelar

```bash
orchestrator task cancel <task_id>
```

O cancelamento não é só uma marca no banco: `TaskService.cancel`
(`tasks/service.py:381`) mata as árvores de processo dos CLIs vivos
(`kill_active`, `agents/process.py:392`), transiciona para `CANCELLED`,
persiste o episódio quando a task já tinha começado a executar, e destrava a
fila do workspace (`tasks/service.py:432-438`).

Duas proteções impedem que um loop já em andamento ressuscite a task:
`TaskRepository.save` não sobrescreve estado terminal
(`tasks/repository.py:192-204`) e `transition` aborta com `CancelledError` se
um cancel concorrente venceu a corrida (`tasks/repository.py:246-280`).

## Retomar

```bash
orchestrator task resume <task_id>
```

`resume` só age em task não-terminal (`tasks/service.py:739-743`; `can_resume`
em `tasks/state_machine.py:146`). Task em `WAITING_FOR_USER` volta ao pipeline
completo por `ANALYZING` (`tasks/state_machine.py:121-128`), preservando a
resposta do usuário registrada em `task.analysis`
(`tasks/service.py:803-818`).

Pelo MCP existe também `orchestrator_message`, para enviar a decisão do usuário
a uma task parada (`mcp/server.py:193-195`).

## Servidor MCP

```bash
orchestrator mcp serve                 # stdio, o transporte padrão
orchestrator mcp serve --transport http --host 127.0.0.1 --port 8765
orchestrator mcp status
orchestrator mcp doctor
orchestrator cursor configure
orchestrator cursor verify
orchestrator agents --json
```

`mcp doctor` responde se o SDK `mcp` está instalado, a saúde do workspace, os
prompts registrados e o nome do servidor (`mcp/server.py:305-319`).

Bind fora de localhost exige `ORCHESTRATOR_MCP_ALLOW_REMOTE=1`, senão o
processo sai com código 2 (`mcp/server.py:268-275`).

## Quando parece travado

Estados longos são normais. O que observar, em ordem:

1. **O estado sozinho não diz nada.** `SELECTING_AGENTS` tem teto de 180 s
   (`tasks/service.py:122`), mas `EXECUTING` pode legitimamente durar até
   `agent_timeout_by_role.executor` (2400 s por padrão) e `VALIDATING` até
   1200 s.
2. **Procure heartbeat.** Cada `agent_progress` traz `elapsed_s` e `pid`
   (`tasks/service.py:2764-2775`) e é persistido, não só ecoado. Sem
   `agent_progress` há mais de uma cadência (20 s para sessão bloqueante, 30 s
   para MCP), suspeite.
3. **Veja se a task está apenas na fila.** `status` de task `QUEUED` traz
   `blocked_by` e `queue_position`. Ela não está travada: está esperando o
   workspace.
4. **Confira o lock.** `.orchestrator/runtime/locks/workspace.write.lock` guarda
   o PID dono. Lock de PID morto é reivindicado automaticamente
   (`execution/locks.py:49-71`); lock de processo vivo significa que outra task
   está mesmo escrevendo.
5. **Watchdog de silêncio.** Agente sem nenhum byte de saída **e** sem tocar no
   workspace por `agent_no_output_timeout_s` é morto, e o stderr recebe o
   marcador `[NO-OUTPUT-WATCHDOG]` (`agents/process.py:365-374`). Achou esse
   marcador no artefato: o agente estava pendurado, não trabalhando.
6. **Fail-fast de infra.** O marcador `[INFRA-FAIL-FAST]` no stderr
   (`agents/process.py:375-381`) indica sandbox do Windows recusando spawn
   (erro 740) ou ritual de multi-agente travado. Nesse caso o runtime rotaciona
   o agente, não insiste.
7. **Quarentena de agente.** Três runs consecutivos falhando em menos de 30 s
   cada, dentro de uma janela de 6 h, tiram o agente das rotações
   (`tasks/service.py:2324-2362`). Binário vivo com serviço morto é a causa
   típica.
8. **Não cancele por impaciência.** Cancelar descarta o trabalho já pago e é a
   principal causa de task perdida registrada na memória do projeto. Antes,
   rode `task status` e `task logs`.

## Onde olhar cada evidência

| Pergunta | Onde |
|---|---|
| O que o agente respondeu? | `.orchestrator/runtime/results/<task_id>/<papel>-<agente>.txt` |
| Qual comando foi disparado? | Tabela `agent_runs`, coluna `command_json` |
| Quais testes rodaram? | Tabela `test_runs`, incluindo as linhas de baseline com `discovery_source` prefixado por `baseline:` |
| Por que reprovou? | Tabelas `validation_rounds` e `validation_issues` |
| O que ficou aprendido? | `.orchestrator/memory/learnings/<task_id>.md` e memórias com `kind=learning` |
| Que patch não entrou (fan-out)? | `.orchestrator/runtime/patches/<task_id>/<sub>.patch` e tabela `subtasks` |

## Desinstalar

```bash
orchestrator uninstall
```

Encaminha para `scripts/Uninstall-Orchestrator.ps1` pelo mesmo caminho de
instalador (`bin/orchestrator.js:137-146` e `372`).
