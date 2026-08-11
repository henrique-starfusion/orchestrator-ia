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

## Baseline Git em árvore suja (0.4.80)

`execution/git_workspace.py` captura o porcelain no início do loop e usa
`changed_files_since` como fallback quando o agente não informa arquivos. O
comparador combina dois sinais:

- mudança do código XY detecta paths limpos no baseline que foram criados,
  modificados ou removidos;
- SHA-256 detecta conteúdo novo nos paths que **já estavam sujos**, mesmo quando
  o XY não muda ou quando uma restauração faz o path sair do porcelain.

O hash é restrito às entradas sujas do baseline. Essa restrição evita varrer a
árvore inteira no início de toda task e basta porque qualquer path limpo que
muda passa a aparecer no porcelain. Raiz e repos Git filhos imediatos usam os
mesmos helpers de snapshot e comparação.

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

## Saúde e reparo de CLI de agente (0.4.63)

Dois módulos novos em `agents/`, com responsabilidades deliberadamente
separadas:

| Módulo | Responsabilidade | O que **não** faz |
|---|---|---|
| `agents/health.py` | Classifica a falha de um `AgentResult` em `install`, `auth` ou `None`; guarda os marcadores e o comando de login de cada agente (`auth_hint`) | Não repara, não decide, não toca em processo |
| `agents/repair.py` | Reinstala o CLI delegando a `scripts/Update-Agents.ps1 -Only <agente>` | Não classifica e não recria os mapas de instalação em Python |

Quem **decide** reparar é `tasks/service.py`, lendo `agent_auto_repair` e
`agent_repair_timeout_s`. A separação existe porque os remédios são opostos:
reinstalar um CLI que só está deslogado apaga a sessão do usuário e não conserta
nada — por isso `auth` vence `install` no empate, e `auth` **nunca** dispara
reinstalação; emite o comando de login.

O reparo delega ao script PowerShell em vez de reimplementar: os mapas curados
(npm, chocolatey, scoop, instalador nativo) já vivem lá, e uma segunda cópia em
Python seria a que ninguém revisa. Host sem PowerShell devolve "reparo
indisponível" e a task segue — não é erro. A reinstalação acontece no máximo
**uma vez por agente por processo**.

O evento `agent_repair` (com `failure_kind`) sai em toda tentativa de reparo e
sempre no caso `auth`, mas **não** é um log de detecção: falha `install` com
`agent_auto_repair` desligado, ou com aquele agente já reparado neste processo,
retorna em silêncio — sem evento. Quem instrumenta em cima desses eventos precisa
saber que ausência de evento não prova ausência de CLI quebrado.

Regra dura, e ela vale independentemente de qualquer configuração:

> **`timed_out` nunca é CLI quebrado.** Quem passou do tempo estava vivo; esse
> caminho já tem dono em `_timeout_issue`, e reinstalar um CLI que trabalhou até
> o timeout é puro desperdício.

Na ausência de qualquer marcador no log, `install` só é arriscado quando o
agente morreu **mudo e rápido** (stdout vazio e duração abaixo de 90 s). O caso
negativo que define esse limite é real: um corrector rodou 17 min, escreveu
20 KB de stderr e saiu `exit=1` — isso é mérito, não infraestrutura.

## Fora do núcleo

OpenWolf, Graphify, Caveman, MCPs globais de terceiros e skills externas são opt-in e **não** são necessários para o runtime.
