# Runtime architecture

Status: **implementado** (MVP 0.2.0)

## Camadas

```text
Installer (Node + PowerShell)
Runtime (Python / orchestrator_runtime)
Agent Adapters (profiles + CliExecutor)
Manager Model (Rules default | LLM opcional)
```

## Persistência

- SQLite: `.orchestrator/data/orchestrator.db`
- Artefatos: `.orchestrator/runtime/results/<task-id>/`
- Export legível: `.orchestrator/memory/episodes/`

## Fluxo

Ver [`task-lifecycle.md`](task-lifecycle.md).

## Pacote

Código em `runtime/src/orchestrator_runtime/`. CLI Node encaminha `run`/`task` via `python -m orchestrator_runtime`.

## MCP (0.3.0)

Transporte Cursor → Runtime: pacote `orchestrator_runtime.mcp` (`orchestrator-ia`).
Não duplica `TaskService`; apenas expõe tools/resources.

Ver [`mcp-integration.md`](mcp-integration.md).

## Learn-then-compact (0.4.14)

Em cada estado terminal após execução, `TaskService._persist_episode` chama `_learn_then_compact` (choke point único): grava a memória `kind=learning` enriquecida (módulo `memory/learnings.py`) + markdown/index + `.wolf/`, **depois** trunca `runtime/results/{id}/*.txt`. O digest compacto (`session_digest`) vai para `orchestrator_result`/`orchestrator_status`; o cliente IDE retém só digest + `learning_path`. Retrieval em `RETRIEVING_MEMORY` inclui `search_memories(kind="learning")`, injetado nos prompts de planner/executor. Config: `policies.json → context_compaction`.

## Fan-out: subtarefas paralelas com escrita (0.4.61)

Até 0.4.60 o runtime era **estritamente sequencial**: um executor por
workspace, serializado pelo `WriteLock`. As chaves
`allow_parallel_read_only_analysis` e `allow_parallel_workspace_writes`
existiam na config desde o começo e **nenhum código as lia**; a tabela
`subtasks` existia e nunca recebia uma linha.

Com `allow_parallel_workspace_writes: true`, a **primeira** passada de execução
pode se dividir:

```text
planner  --decomposition_prompt-->  {"subtasks":[{id,title,scope,instruction}]}
                                          |
              +---------------------------+---------------------------+
              v                                                       v
   worktree s1 (git worktree add --detach)                 worktree s2
   agente escreve só no seu escopo                         idem
              |                                                       |
        git add -A + git diff --cached  ------> patch          patch
                                          |
                       git apply --check  &&  git apply   (árvore real)
```

Decisões que sustentam isso:

- **Worktree, não pasta compartilhada.** O bug-077 (printbee) registrou seis
  quase-arrastões num dia com agentes lado a lado: `git add -A` de um leva o
  trabalho não commitado do outro. Dentro de um worktree privado o perigo some
  por construção.
- **Fusão tudo-ou-nada.** `git apply --check` antes de escrever. `--3way`
  resolveria mais casos, mas em conflito deixa marcadores no working tree — um
  merge pela metade na árvore real, justamente onde há trabalho alheio. Patch
  que não passa vira subtarefa `conflict`, com o `.patch` preservado em
  `.orchestrator/runtime/patches/<task>/` para a próxima iteração.
- **Escopo disjunto é requisito, não sugestão.** Escopos que se sobrepõem (ou
  não declarados) são **fundidos** numa subtarefa só antes de gastar agente —
  fundir preserva o trabalho declarado; descartar perderia requisito.
- **Executor próprio por subtarefa.** Não é preciosismo: o watchdog de silêncio
  (bug-086) sonda o workspace para decidir se o agente está vivo, e uma sonda
  apontada para a árvore principal veria "nada mudou" enquanto a subtarefa
  escreve no worktree — mataria agentes vivos.
- **Só na primeira passada.** Correção existe para fechar issue específica do
  validator; dividir isso entre agentes cegos uns aos outros multiplica o
  conflito, não o trabalho.
- **Thread por subtarefa.** `adapter.run` é `async` mas o `CliExecutor` por
  baixo é bloqueante: um `gather` direto serializaria tudo e ainda travaria o
  event loop.

Requisitos e limites: repo git com pelo menos um commit (sem HEAD não há base
para worktree nem diff — cai no sequencial), `max_parallel_subtasks` (padrão 4),
e uma execução por workspace continua valendo — o fan-out acontece **dentro**
de uma task, não entre tasks. Registro em `subtasks`
(`merged`/`conflict`/`empty`/`failed`) e nos eventos `agent_started`/
`agent_completed` com `mode=parallel_subtasks`.

## Fora do núcleo

OpenWolf, Graphify, Caveman, MCPs globais de terceiros e skills externas são opt-in e **não** são necessários para o runtime.
