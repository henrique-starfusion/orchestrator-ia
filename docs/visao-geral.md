# Visão geral

## O que é

`@starfusion/orchestrator` (repositório `bootstrap-agents`) é um **orquestrador
multiagente instalável em qualquer repositório**. Ele não é uma aplicação de
negócio: os projetos-alvo são workspaces onde ele executa trabalho.

O pacote tem duas camadas, declaradas no próprio CLI (`bin/orchestrator.js:5-8`):

- **Instalador** — PowerShell (`scripts/Install-Orchestrator.ps1`), invocado
  pelo wrapper Node.
- **Runtime persistente** — Python (`runtime/src/orchestrator_runtime/`),
  invocado como `python -m orchestrator_runtime` (`bin/orchestrator.js:337`).

O nome do pacote e os binários expostos (`orchestrator`, `mao`) estão em
`package.json:14-17`.

## Que problema resolve

Um agente de CLI (Claude Code, Codex, Gemini, Kimi, OpenCode) executa o que se
pede e responde. Ele não garante que:

- a tarefa foi classificada e ganhou critérios de aceitação verificáveis;
- alguém **diferente do executor** revisou o resultado;
- a suíte de testes do projeto rodou antes e depois;
- a documentação afetada foi revisada;
- o que foi decidido ficou registrado para a próxima tarefa;
- duas sessões simultâneas não escrevem no mesmo workspace ao mesmo tempo.

O orquestrador transforma "um prompt vira uma resposta" em "uma task vira um
resultado verificado". Ele mantém uma máquina de estados
(`runtime/src/orchestrator_runtime/tasks/state_machine.py:37`), gates
determinísticos (`validation/deterministic.py`), validação independente por um
segundo agente (`RulesRouter.select_plan`, `routing/manager.py:64-80`), e
persistência em SQLite (`memory/database.py`).

Um só invariante resume o produto: **`COMPLETED` só sai pelo portão de
conclusão** (`CompletionGate.can_complete`,
`runtime/src/orchestrator_runtime/validation/deterministic.py:270-289`), que
exige testes passando, validação aprovada, score acima do limiar, zero blocking
issue e revisão documental com `validation == "passed"`.

## Atores

| Ator | O que é | Onde vive no código |
|---|---|---|
| **Agente principal (chat)** | O agente com quem a pessoa conversa (Cursor, Claude Code, Codex...). Não executa a tarefa: dispara o runtime e acompanha. | Regras em `.cursor/rules/multiagent-orchestrator.mdc`; texto embutido em `runtime/src/orchestrator_runtime/cli.py:357-411` |
| **Runtime** | O orquestrador de verdade: máquina de estados, fila, gates, testes, memória. | `TaskService` (`tasks/service.py:117`) |
| **Agentes delegados (workers)** | CLIs spawnados pelo runtime em papéis (`planner`, `executor`, `corrector`, `validator`, `skill_selector`). | `AgentRegistry` (`agents/__init__.py:74`), `ProfileCliAdapter` (`agents/base_adapters.py:60`) |
| **Instalador** | Escreve `.orchestrator/`, detecta CLIs, gera adaptadores, registra MCP, propaga updates para a frota. | `scripts/Install-Orchestrator.ps1`, `scripts/Generate-Adapters.ps1`, `scripts/Propagate-OrchestratorUpdate.ps1` |
| **Clientes MCP** | IDEs/CLIs que falam com o runtime pelo servidor `orchestrator-ia` via JSON-RPC stdio. | `mcp/server.py:21` (`SERVER_NAME`), tools em `mcp/tools.py` |
| **Cursor** | Cliente IDE, explicitamente **não** worker: o adapter recusa selecioná-lo como papel. | `CursorClientAdapter` (`agents/__init__.py:50-71`), guarda em `routing/manager.py:111-112` |

## Vocabulário do domínio

**Task** — unidade de trabalho persistida. Id de 12 hex
(`new_task_id`, `tasks/models.py:25-26`), com prompt, tipo, critérios de
aceitação, restrições, estado, iteração e score. Modelo: `TaskRecord`
(`tasks/models.py:113`).

**Estado** — posição da task na máquina de estados. Dezessete valores em
`TaskState` (`tasks/state_machine.py:10-27`); terminais são só quatro:
`COMPLETED`, `INCOMPLETE`, `FAILED`, `CANCELLED` (`state_machine.py:30-35`).
`WAITING_FOR_USER` **não** é terminal — `can_resume` devolve `True` para ele
(`state_machine.py:146-147`).

**Iteração** — uma volta completa do ciclo executar → testar → validar. O
contador é `TaskRecord.iteration`, incrementado no topo do laço
(`tasks/service.py:956`), e o teto vem de `maximum_iterations`
(`tasks/service.py:944`). Continuação de plano incompleto **não** consome
iteração: o contador é devolvido antes do `continue`
(`tasks/service.py:1302`).

**Papel (role)** — função que um agente exerce numa task: `planner`,
`executor`, `corrector`, `validator`, `tester`, `skill_selector`. Os papéis de
worker estão em `WORKER_ROLES` (`agents/__init__.py:14`); `tester` é sempre o
runtime, não um CLI (`routing/manager.py:90`). Cada papel tem timeout próprio
(`config.py:22-31`).

**Loop** — roteiro de execução escolhido pelo pedido, com etapas obrigatórias e
critérios próprios. Oito loops registrados em `LOOPS`
(`planning/loops.py:68`): `bug`, `ui-probe`, `review`, `mvp`, `landing`,
`conteudo`, `saas`, `research`. Um loop define `task_type` quando a heurística
de palavra-chave é menos específica (`planning/analyzer.py:144-145`) e injeta
seu briefing no prompt do executor (`TaskService._loop_block`,
`tasks/service.py:1903`).

**Workspace** — a raiz do projeto onde a task roda; sempre um diretório com
`.orchestrator/` (`resolve_orchestrator_root`, `config.py:98-104`). A fila é
**por workspace**: uma task em execução bloqueia as demais do mesmo
`project_path` (`find_active_execution`, `tasks/repository.py:154`).

**Frota** — o conjunto de projetos onde o orquestrador está instalado,
registrado em `%LOCALAPPDATA%\StarFusion\orchestrator\projects.json`
(`Get-ProjectRegistryPath`, `scripts/Orchestrator.Common.ps1:1088-1094`). O
update do pacote propaga para todos eles
(`scripts/Propagate-OrchestratorUpdate.ps1`).

**Critério de aceitação (AC)** — condição verificável da entrega.
`AcceptanceCriterion` (`tasks/models.py:45`) carrega um `kind` tipado
(`CriterionKind`, `tasks/models.py:29-37`) que decide qual verificador roda no
validador determinístico (`validation/deterministic.py:124-132`). Critério vago
é rejeitado na validação do modelo (`tasks/models.py:54-60`).

**Score** — nota da rodada de validação, entre 0 e 1. O limiar de conclusão
padrão é `0.9` (`config.py:18`), aplicado por `CompletionGate`
(`validation/deterministic.py:266-268`).

**Evento** — registro estruturado do que aconteceu. Vinte tipos em `EventType`
(`events.py:13-35`), persistidos em `task_events` e ecoados em **stderr**,
nunca em stdout — stdout é reservado ao JSON-RPC do MCP (`events.py:70-71`).

**Learning** — aprendizado durável extraído no fim da task, salvo antes de
qualquer compactação de artefato (`_learn_then_compact`,
`tasks/service.py:3024-3084`).
