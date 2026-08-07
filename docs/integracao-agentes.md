# Integração com os agentes

## Como um agente é acionado

Não existe código específico por CLI. Cada agente é descrito por um JSON em
`.orchestrator/agents/profiles/`, carregado por `AgentRegistry._load`
(`agents/__init__.py:81-105`) e executado por `ProfileCliAdapter`
(`agents/base_adapters.py:60`).

A linha de comando é montada em `build_command`
(`agents/base_adapters.py:96-133`) nesta ordem:

```text
<id do agente> <invoke.subcommand...> <invoke.sandbox_flags...>
  [model_flag] [modelo] [invoke.prompt_flag] [prompt] <extra_args>
```

O `model_flag` e o modelo vêm de `models.json`, resolvidos por
`RulesRouter.resolve_model_candidates` (`routing/manager.py:146`), não do
profile.

## Os cinco CLIs suportados como worker

Valores conferidos nos profiles vivos em `.orchestrator/agents/profiles/`.

| Agente | Subcomando | Flag de prompt | Flags de sandbox | Timeout padrão | Verificado |
|---|---|---|---|---|---|
| `claude` | nenhum | `-p` | `--permission-mode bypassPermissions` | 2400 s | sim |
| `codex` | `exec` | nenhuma (prompt posicional) | `--sandbox workspace-write --skip-git-repo-check` | 2400 s | sim |
| `gemini` | nenhum | `-p` | nenhuma | 1200 s | não (extraído de documentação) |
| `kimi` | nenhum | `-p` (exige valor: `prompt_stdin: false`) | nenhuma | 2400 s | sim |
| `opencode` | `run` | nenhuma (prompt posicional) | nenhuma | 2400 s | sim |

Linha de comando resultante, na prática:

```text
claude   --permission-mode bypassPermissions --model <alias> -p "<prompt>"
codex    exec --sandbox danger-full-access --skip-git-repo-check -m <modelo> "<prompt>"
gemini   -m <modelo> -p "<prompt>"
kimi     -m <modelo> -p "<prompt>"
opencode run --model <modelo> "<prompt>"
```

Notas de comportamento registradas nos próprios profiles:

- **claude**: `bypassPermissions` substituiu `acceptEdits` porque este último
  auto-aceitava edição mas ainda pedia aprovação para Bash — sem terminal, o
  agente ficava pendurado até o timeout.
- **codex**: no Windows, `workspace-write` é trocado por `danger-full-access`
  em tempo de execução (`agents/base_adapters.py:108-111`), porque
  `CreateProcessAsUserW` falha com erro 740 sem elevação.
- **kimi**: `sandbox_flags` vazio de propósito — o CLI recusa `--auto` e
  `--yolo` junto com `-p`. E `prompt_stdin: false`, porque `-p` exige valor;
  prompt grande demais falha com erro explicado em vez de virar um `-p` vazio.
- **gemini**: `verified: false`; o registro trata agente não verificado como
  experimental (`agents/__init__.py:101`).

## Cursor não é worker

`cursor.json` tem `kind: ide-client` e `executable: false`. O registro
substitui qualquer profile com esse `kind` por `CursorClientAdapter`
(`agents/__init__.py:94-96`), cujo `detect()` devolve `available: false` e
`capabilities()` devolve zero papéis (`agents/__init__.py:56-71`). Tentar
forçar `--executor cursor` levanta `ValueError`
(`routing/manager.py:111-112`).

## Preferência por papel

`AgentRegistry.prefer_mvp_order` (`agents/__init__.py:124-142`) define a ordem
antes de qualquer pontuação:

| Papel | Ordem |
|---|---|
| planner | claude, codex, opencode, gemini, kimi |
| executor | codex, claude, opencode, gemini, kimi |
| corrector | codex, claude, opencode, gemini, kimi |
| validator | claude, codex, opencode, gemini, kimi |

`CapabilityScorer.score` (`routing/manager.py:23-38`) reordena por afinidade —
claude soma no planner, codex soma no executor — e o CLI que já está atendendo
o usuário é evitado como executor (`routing/manager.py:59-62`).

## O que o install e o update configuram em cada projeto

`Generate-Adapters.ps1` copia, por vendor detectado, o conteúdo de
`package/template/adapters/<vendor>/` para a raiz do projeto
(`Generate-Adapters.ps1:30-43` escolhe os vendors a partir de
`.orchestrator/agents/detected.json`).

| Vendor | Arquivos gerados no projeto |
|---|---|
| claude | `.claude/README.md`, `.claude/skills/call-agent/SKILL.md`, `CLAUDE.md`, bloco anexado em `CLAUDE.md` |
| codex | `.codex/README.md`, seções anexadas em `AGENTS.md` |
| cursor | `.cursor/mcp.json.example`, seis regras em `.cursor/rules/`, `CURSOR.md` |
| gemini | `.gemini/README.md`, `GEMINI.md` e seções |
| kimi | `.kimi/README.md`, `KIMI.md` e seções |
| opencode | `.opencode/README.md`, seções anexadas em `AGENTS.md` |

Regras entregues ao Cursor: `call-agent.mdc`, `git-workflow.mdc`,
`multiagent-orchestrator.mdc`, `orchestrator.mdc`, `runtime.mdc`,
`token-economy.mdc`, `version-bump.mdc`.

Arquivo terminado em `.section.md` é **anexado** ao `.md` de mesmo nome na raiz
e, se o marcador da primeira linha já existir, o bloco é **sincronizado** —
sem duplicar e sem congelar o texto no template
(`Generate-Adapters.ps1:58-101`).

Além dos adaptadores, o install e o update escrevem a estrutura completa de
`.orchestrator/` a partir de `package/template/.orchestrator/`: `config/` com os
sete JSONs, `agents/profiles/` com os seis profiles, `agents/*-subagents/` com a
persona `orquestrador`, `hooks/`, `mcp/`, `memory/`, `orchestration/`,
`runtime/` e `skills/`.

## Registro do MCP por projeto

Dois caminhos, conforme o cliente:

- **Cursor**: `.cursor/mcp.json`, escrito por
  `write_cursor_mcp_config` (`mcp/cursor_config.py`) via
  `orchestrator cursor configure` (`cli.py:339-415`). O mesmo comando garante a
  regra `multiagent-orchestrator.mdc` com texto embutido no CLI
  (`cli.py:357-411`).
- **Claude Code e Kimi Code**: `.mcp.json` na raiz, escrito por
  `Configure-AgentMcp.ps1`. O script documenta o motivo: os dois CLIs leem
  `.mcp.json` (chave `mcpServers`) e, antes disso, nunca tinham as tools
  `orchestrator_*` disponíveis (`Configure-AgentMcp.ps1:6-19`).

A entrada é registrada com a chave `orchestrator-ia`, mesclando com servidores
MCP já presentes e removendo a chave legada `multiagent-orchestrator`
(`Configure-AgentMcp.ps1:86-89`). Ela não passa `--project`: os clientes
spawnam o servidor com o cwd no workspace e o runtime resolve o projeto pelo
cwd.

Se o comando `orchestrator` estiver no PATH, a entrada usa
`cmd /c orchestrator mcp serve --transport stdio`; senão, cai para
`cmd /c <node> <bin/orchestrator.js> mcp serve --transport stdio`
(`Configure-AgentMcp.ps1:44-70`).

## Detecção e sondagem

`Detect-Agents.ps1` grava `.orchestrator/agents/detected.json` com os CLIs
presentes no PATH; `Probe-Agents.ps1` confere as flags que cada um aceita e
grava `.orchestrator/agents/probe-results.json`. O update só passou a chamar a
sondagem a partir da 0.4.32 — antes, o `probe-results.json` dos projetos
propagados ficava congelado na data da instalação
(`Install-Orchestrator.ps1:305-312`).

No runtime, a detecção é mais simples: `ProfileCliAdapter.detect` chama
`which(self.id)` (`agents/base_adapters.py:82-91`). A função `which`
(`agents/process.py:420-433`) tem um fallback para Windows que procura em
`%APPDATA%\npm` e no prefixo global do npm, porque CLIs instalados fora do PATH
do processo MCP ficavam eternamente indisponíveis.

## Anti-recursão: agente filho

O mecanismo tem três partes.

**1. Marca no processo filho.** `CliExecutor.run` sempre define
`ORCHESTRATOR_CHILD_AGENT=1` no ambiente do subprocesso
(`agents/process.py:156-157`) e restaura o valor anterior no `finally`
(linhas 358-361).

**2. Bloqueio de delegação aninhada.** No começo de `run`, se o processo atual
já é filho e `allow_nested` é falso, o executor levanta `RecursionBlockedError`
(`agents/process.py:150-153`). Um agente delegado não consegue spawnar outro
agente pelo runtime.

**3. Flag por valor, não por presença.** `is_child_agent`
(`agents/process.py:57-65`) trata string vazia e `0` como "não é filho". O
comentário registra o defeito que motivou isso: shells herdavam a variável
vazia, o agente principal se achava delegado e recusava orquestrar, fazendo
tudo inline.

Complemento no prompt: `_child_agent_restriction_block`
(`tasks/service.py:1871-1886`) injeta a proibição explícita de `spawn_agent`,
`wait_agent`, `collab Wait`, `Tool(Agent)`, `Task` e ritos de multi-agente. O
comentário do método registra que a checagem antiga era feita no ambiente do
processo **pai** (o MCP), então o bloco nunca entrava no prompt e o agente
seguia rituais de subagente até travar.

O bloco vai **antes** das skills no prompt do executor
(`tasks/service.py:1927-1931`), para o modelo não se comprometer com um plano de
subagentes antes de ler a proibição.

Personas de agente do projeto (`.claude/agents/`, `.codex/agents/`,
`.kimi-code/agents/`, `.opencode/agent/`) entram no prompt como **guia de escopo
e convenção**, com a delegação explicitamente excluída
(`_agents_block`, `tasks/service.py:1794-1818`).

As duas suítes de teste também isolam a variável, porque a própria suíte pode
rodar sob o orquestrador: `tests/Run-AllTests.ps1:5-9` e
`runtime/tests/conftest.py:11-17`.
