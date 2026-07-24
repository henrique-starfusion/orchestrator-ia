# Auditoria 0.4.8 — Gap de auto-dispatch (ainda exige pedido explícito)

Data: 2026-07-23 · Tipo: complex_analysis · Task orquestrador: `d511b77505a0` (CANCELLED — executor stdout vazio; relatório fechado no chat com evidência do planner + verificação local)

## Sumário executivo

O wording **já está correto** em 0.4.7/0.4.8 (`Modo padrão: orquestrador … sem o usuário pedir`). Isso **não basta** porque:

1. Rules do Cursor são **advisory** (não bloqueiam tool calls).
2. As tools MCP `orchestrator_run` / `delegate` / `analyze` em `server.py` **não têm docstring** — o modelo não vê o contrato de default no discovery.
3. No PrintBee, `decision_tree.mdc` e `agents_overview.mdc` mandam usar **subagentes locais** antes de alterar código, **sem citar** `orchestrator_run` — conflito direto com a rule de modo padrão.

Resultado: o chat só chama o orquestrador quando o usuário pede.

## Cadeia causal pós-0.4.8

```
Pedido do usuário (tarefa)
  → Cursor injeta rules (alwaysApply) incluindo modo padrão OK
  → Também injeta decision_tree / agents_overview (PrintBee) → "3 subagentes"
  → Modelo escolhe caminho de menor atrito: Task/edição inline
  → Descrições MCP de orchestrator_run vazias → não reforçam default
  → Sem hooks → ninguém veta a edição
  → Usuário precisa pedir "use o orquestrador"
```

## Achados

### H1 — CONFIRMADO: rules são advisory; sem hooks

- `.cursor/` em bootstrap-agents: só `mcp.json` + `rules/` — **zero** `hooks/`.
- Cursor não impede `Write`/`Shell` sem `orchestrator_run` ativo.

### H2 — CONFIRMADO: front-controller MCP sem contrato na tool

`runtime/src/orchestrator_runtime/mcp/server.py` — funções `orchestrator_run` / `orchestrator_delegate` / `orchestrator_analyze` **sem docstring**. FastMCP usa a docstring como descrição vista no tool discovery. O modelo vê parâmetros, não a obrigação de chamar antes de editar.

Prompts MCP (`mcp/prompts.py`) mencionam `orchestrator_run` só para "tarefa complexa" — linguagem fraca e prompts são opt-in.

### H3 — CONFIRMADO (parcial): Task como rota paralela

- `call-agent.mdc` (PrintBee/bootstrap): "use Task with model=…" como mecanismo Cursor.
- `multiagent-orchestrator.mdc` já diz Task só fallback — mas `call-agent` + `decision_tree` competem na prática.

### H4 — CONFIRMADO: PrintBee decision_tree / agents_overview bypassam o runtime

`D:\StarFusion\printbee\.cursor\rules\decision_tree.mdc:2-7`:

- "Nova atividade de execução? Rode no mínimo 3 subagentes antes de alterar"
- Não cita `orchestrator_run`.

`agents_overview.mdc:3-4`: mesma diretriz de 3 subagentes / `architect_solutions` como default de sessão.

Enquanto isso `multiagent-orchestrator.mdc` no PrintBee **já tem** modo padrão 0.4.8 — as rules de produto **vencem por especificidade** na leitura do modelo.

### H5 — CONFIRMADO (operacional): workspace = rules daquele projeto

Abrir `printbee` como raiz usa só `.cursor/rules` do PrintBee. Propagação via `orchestrator update` já colocou o modo padrão; o gap restante é o **conflito com decision_tree**, não a ausência da rule.

### H6 — SECUNDÁRIO: juízo de "trivial"

Mesmo com gatilhos claros, o modelo ainda pode classificar bug fix como "simples". Sem enforcement, isso vira inline.

## Por que o wording 0.4.7 falhou sozinho

| Camada | Estado 0.4.8 | Enforcement? |
|---|---|---|
| Rule modo padrão | OK | Não (advisory) |
| Descrição tool MCP | Vazia | Não |
| decision_tree PrintBee | Conflita | Empurra bypass |
| Hooks Cursor | Ausentes | Não |

## Patches P0 / P1

| # | Pri | Ação |
|---|---|---|
| P0a | P0 | Docstrings em `server.py` para `orchestrator_run`/`delegate`/`analyze`: DEFAULT obrigatório; chamar antes de editar |
| P0b | P0 | PrintBee: `decision_tree.mdc` + `agents_overview.mdc` — primeiro passo = `orchestrator_run`; subagentes só via runtime |
| P0c | P0 | Rule template: linha "primeira tool de trabalho = orchestrator_run" |
| P1 | P1 | Hook Cursor (quando estável) veto de edição sem task ativa |
| P1 | P1 | Teste smoke: docstring MCP contém "DEFAULT" / "sem o usuário pedir" |

## Critérios de aceitação

1. Relatório presente (este arquivo).
2. `server.py` `orchestrator_run` docstring contém "DEFAULT" e "sem o usuário pedir".
3. PrintBee `decision_tree.mdc` cita `orchestrator_run` como passo 1 de execução.
4. `Test-CursorDefaultOrchestration` / novo smoke de docstring MCP verdes.
5. Bump + `orchestrator update -Force` nos consumidores.

## Nota sobre a task `d511b77505a0`

Planner (fable) produziu plano H1–H6 coerente. Executor/corrector retornaram stdout de 2 bytes — falha de agente CLI, não de diagnóstico. Entrega fechada no cliente IDE com a mesma evidência.
