# Design — Skill `call-agent` + Agent Profiles declarativos

**Data:** 2026-07-20
**Status:** aprovado pelo usuário
**Objetivo:** qualquer chat (Claude Code, Codex, Cursor, Gemini, Kimi, OpenCode) sabe COMO invocar o CLI de qualquer agente detectado — e adicionar um CLI novo exige apenas um arquivo JSON, zero código.

## Decisões fechadas (com o usuário)

1. **Skill fina + profiles JSON.** O conhecimento de invocação vive em `agents/profiles/<cli>.json` (dados canônicos). A skill `call-agent` ensina o fluxo e manda ler o profile. CLI novo = JSON novo, skill intacta.
2. **Stub por vendor + canônica.** Skill canônica em `.orchestrator/skills/call-agent/`. `Generate-Adapters.ps1` gera stub nativo por vendor detectado (`.claude/skills/call-agent/SKILL.md` com frontmatter, seção no `AGENTS.md`, `.cursor/rules/call-agent.mdc`, linha nos README `.gemini/`/`.kimi/`). Stub aponta pra canônica — zero duplicação de conteúdo.
3. **Escopo inicial: 6 CLIs** — claude, codex, gemini, kimi, opencode, cursor (hint-only). Demais entram depois e provam a tese "CLI novo = só JSON".

## Componentes

### 1. Schema — `package/schemas/agent-profile.schema.json`

Contrato do adapter. Campos:

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | string | nome do agente (= binário quando `kind: cli`) |
| `kind` | `cli` \| `ide-hint` | ide-hint = sem CLI (Cursor): só instrução |
| `invoke.subcommand` | string[] | args fixos pra modo não-interativo (ex.: `["exec"]` codex, `["-p"]` claude) |
| `invoke.prompt_via` | `arg` \| `stdin` | como o prompt entra. v1: só `arg` (stdin = decisão aberta, adiada) |
| `invoke.sandbox_flags` | string[] | opcionais de permissão/sandbox (ex.: `--full-auto`) — nunca aplicados por padrão |
| `output.format` | `text` \| `json` \| `stream-json` | formato de saída padrão |
| `output.json_flags` | string[] | flags pra forçar saída JSON quando suportado |
| `exit_codes.success` | int | default 0 |
| `timeout_default_s` | int | timeout sugerido |
| `verified` | bool | true = testado neste host; false = extraído de docs |
| `notes` | string | quirks |

**Não duplica `models.json`:** profile = mecânica (COMO invocar); `models.json` continua dono de `model_flag`, aliases e `task_map` (QUAL modelo por tarefa). O dispatch junta os dois.

### 2. Profiles — `package/template/.orchestrator/agents/profiles/*.json`

| CLI | Invocação não-interativa | verified |
|---|---|---|
| claude | `claude -p "<prompt>" --model <alias>` (`--output-format json` opcional) | true (host) |
| codex | `codex exec "<prompt>" -m <model>` (`--full-auto` opcional) | true (host) |
| gemini | `gemini -p "<prompt>" -m <model>` | false |
| opencode | `opencode run "<prompt>" --model <m>` | true (host) |
| kimi | best-effort de docs | false |
| cursor | `kind: ide-hint` — instrui `Task model="<slug>"` | n/a |

### 3. Skill canônica — reescrever `.orchestrator/skills/call-agent/SKILL.md`

Fluxo pro chat:
1. Classificar `task_class` (ver `config/models.json`).
2. Resolver rota: `orchestrator route --task-class <c> --client <x> --json` (ou ler `models.json` direto).
3. Ler `agents/profiles/<client>.json`.
4. Montar comando: profile.invoke + model_flag/alias da rota + prompt escopado.
5. Executar com timeout do profile; nunca aplicar `sandbox_flags` sem pedido explícito.
6. Salvar resultado em `runtime/results/`, interpretar exit code.

Inclui: exemplos concretos por CLI, regra anti-recursão (`ORCHESTRATOR_CHILD_AGENT=1` no ambiente do filho; se já setada, não delegar), aviso de profile `verified: false`.

### 4. Stubs por vendor — templates em `package/template/adapters/`

- `claude/.claude/skills/call-agent/SKILL.md` — frontmatter `name` + `description` (auto-trigger) + corpo ~5 linhas apontando canônica e profiles.
- `codex/AGENTS-call-agent-section.md` → anexada ao `AGENTS.md` (codex/opencode) somente se o marcador `<!-- orchestrator:call-agent -->` ainda não existir no arquivo (append idempotente).
- `cursor/.cursor/rules/call-agent.mdc`.
- linha nos README de `.gemini/` e `.kimi/`.

Gerados por `Generate-Adapters.ps1` apenas pra vendors detectados; não sobrescreve existentes sem `-Force` (padrão atual).

### 5. Dispatch consome profiles — `scripts/Invoke-RoutedAgent.ps1`

Substituir o bloco if/elseif por: carregar `agents/profiles/<client>.json`; montar args de `invoke.subcommand` + `model_flag` (da rota) + prompt. Erro instrutivo se profile ausente (`orchestrator update`) ou CLI fora do PATH. Warning se `verified: false`. (Era a Fase 1 do STATUS — mesma entrega.)

### 6. Teste — `tests/Test-AgentProfiles.ps1`

- Valida os 6 profiles contra o schema (estrutura + campos obrigatórios).
- Dry-run do dispatch por CLI monta a linha de comando esperada (golden strings).
- Integra em `Run-AllTests.ps1`.

## Erros

| Condição | Comportamento |
|---|---|
| CLI fora do PATH | erro com comando de instalação sugerido |
| Profile ausente | erro apontando `orchestrator update` |
| `verified: false` | warning no dispatch, prossegue |
| task_class desconhecida | erro existente do Resolve-ModelRoute (mantido) |

## Fora de escopo (v1)

- `prompt_via: stdin` (decisão aberta — adiar até um CLI exigir).
- Task envelope + loop de validação (Fase 2 do STATUS).
- Profiles dos outros 14 CLIs detectáveis.
