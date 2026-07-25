# Design — Fila de tasks por workspace (0.4.19)

## Problema

Duas submissões `orchestrator_run` no mesmo projeto competem pelo WriteLock. A segunda fica `blocked_by_lock` sem dequeue — parece travada e o chat cancela.

## Decisão

- Fila **por `project_path`** (não global).
- Dequeue **automático** FIFO ao liberar o lock (fim ou cancel da ativa).
- Estado novo: `QUEUED`.

## Fluxo

1. `create_task` → `RECEIVED`.
2. `run_task`: se workspace ocupado (`lock` busy / outra task em `_running_tasks` ou status ativo) → transição `RECEIVED → QUEUED`, `error=queued_behind:<active_id>|pos=N`, evento `TASK_QUEUED`. Retorna sem falhar.
3. Se livre → fluxo atual (adquire lock, `_execute_loop`).
4. Ao sair de `run_task` (qualquer terminal / saída do `with lock`): `_dequeue_next(project_path)` → próxima `QUEUED` mais antiga por `created_at` → `QUEUED → RECEIVED` (ou direto ANALYZING) e `run_task` em background (thread/asyncio create_task).
5. Cancel de `QUEUED` → `CANCELLED` (não dispara dequeue da ativa). Cancel da ativa → libera lock → dequeue.

## MCP / status

`orchestrator_run` e `orchestrator_status` expõem:

- `status: QUEUED`
- `queue_position` (1-based)
- `blocked_by` (task_id ativa)
- `message` legível

## Fora de escopo

- Fila global entre projetos
- Prioridade / jump-the-queue
- Persistência de fila fora do status SQLite

## Critérios de aceitação

- AC1: 2ª `run` no mesmo workspace → `QUEUED`, não `FAILED` / não `blocked_by_lock` mudo
- AC2: ao completar a 1ª, a 2ª inicia sozinha (`ANALYZING`+)
- AC3: projetos distintos podem executar em paralelo
- AC4: cancel da enfileirada não mata a ativa; cancel da ativa inicia a próxima
- AC5: testes unitários determinísticos + docs troubleshooting/changelog
