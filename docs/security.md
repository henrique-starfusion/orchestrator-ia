# Security — Orquestrador IA Multiagente

Status: **implementado** (MCP local / stdio) · HTTP remoto: **experimental** · auth remota: **planejado**

Política de reporte (aba Security do GitHub): [`.github/SECURITY.md`](../.github/SECURITY.md).

## Visão geral

O Orquestrador IA Multiagente trata o Cursor e outros chats como **clientes** do runtime. A superfície sensível é o servidor MCP + o workspace do projeto. Controles abaixo assumem transporte **stdio** local (padrão).

## MCP

| Controle | Comportamento |
|----------|----------------|
| Bind | Padrão `127.0.0.1` apenas; bind remoto exige `ORCHESTRATOR_MCP_ALLOW_REMOTE=1` |
| Workspace allowlist | **Estrita**: só `default_workspace` do MCP e subpaths; path absoluto externo é rejeitado mesmo com `.orchestrator/` |
| Shell genérico | Sem tool de shell arbitrário |
| Agentes / roles | Só do registry; Cursor **não** é worker CLI |
| `read_only` | Em `orchestrator_delegate`, bloqueia roles de escrita |
| Prompts | Limitados em tamanho |
| Secrets | Logs, resultados e echo live passam por `redact()` |
| Rede / deps | `allow_network` e install de deps **rejeitados** (não são no-op) |
| Recursão | `ORCHESTRATOR_CHILD_AGENT` impede delegação aninhada |
| Overrides | `planner` / `executor` / `validator` explícitos têm precedência sobre `routing=automatic` |
| `fake_agents` | **Bloqueado** na superfície MCP (CLI/`ORCHESTRATOR_ALLOW_FAKE_AGENTS` só para CI) |
| Validação | `require_independent_validation`: falha se não houver validator ≠ executor |
| Stdio | Heartbeat/`[exec]`/eventos verbose vão para **stderr** (stdout só JSON-RPC) |
| Dados | `.orchestrator/data` tenta `chmod 0o700` (Unix; best-effort no Windows) |
| Fingerprint | `orchestrator_health` / `version --json` expõem `code_fingerprint` para detectar MCP stale |

## Políticas e configuração

- Tools MCP **não** podem sobrescrever `config/policies.json` (limites do runtime).
- Fonte canônica de regras: `.orchestrator/` no projeto-alvo.
- Instalação/update são determinísticos (templates + PowerShell); não use agentes de IA para “inventar” a árvore de config.

## Boas práticas para quem usa o projeto

1. Mantenha o orquestrador atualizado (`orchestrator update` / release tags).
2. Após update do runtime, **recarregue o Cursor** (processo MCP cacheia código).
3. Não habilite bind remoto nem `ORCHESTRATOR_ALLOW_FAKE_AGENTS` em máquinas de desenvolvimento compartilhadas.
4. Trate artefatos em `.orchestrator/runtime/` e DB local como sensíveis ao workspace.
5. Revise overrides de agentes em `orchestrator_run` antes de tarefas com escrita.

## Relacionado

- [`docs/mcp-integration.md`](mcp-integration.md)
- [`docs/mcp-tool-reference.md`](mcp-tool-reference.md)
- [`docs/troubleshooting.md`](troubleshooting.md)
- [`.github/SECURITY.md`](../.github/SECURITY.md) — como reportar vulnerabilidades
