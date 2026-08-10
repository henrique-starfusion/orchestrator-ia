# Solução de problemas — Orquestrador IA Multiagente

Guia operacional para falhas comuns do **Orquestrador IA Multiagente** (`@starfusion/orchestrator`).

Quickstart: [`quickstart-oneliner.md`](quickstart-oneliner.md)

---

## Diagnóstico rápido

```bash
orchestrator status
orchestrator verify
orchestrator mcp doctor
orchestrator cursor verify
```

### MCP / Cursor

| Sintoma | Ação |
|---|---|
| Tools MCP ausentes no chat | `orchestrator cursor configure` e reiniciar Cursor |
| `mcp` Python ausente | `pip install -e runtime/` (inclui `mcp>=1.6,<2`) |
| Runtime unavailable | `orchestrator install` no projeto; checar `.orchestrator/` |
| HTTP bind recusado | use `127.0.0.1` ou `ORCHESTRATOR_MCP_ALLOW_REMOTE=1` |
| `Unexpected token '[heartbeat]'` / `transport_error` | stdout poluido no stdio; atualize o runtime (heartbeat em stderr) e **reload Cursor** |
| Log `[error] INFO Processing request` + `undefined` | Cosmetico: Cursor trata stderr como erro; conexao OK se houver `Successfully connected` |

```bat
orchestrator-ia.bat status -ProjectPath C:\dev\projeto
orchestrator-ia.bat verify -ProjectPath C:\dev\projeto
orchestrator-ia.bat analyze -ProjectPath C:\dev\projeto
```

Logs:

```text
.orchestrator/runtime/validations/*.log
.orchestrator/runtime/reports/installation-report.md
```

Cache do one-liner PowerShell:

```text
%LOCALAPPDATA%\StarFusion\multiagent-orchestrator
```

---

## 0.4.20 — Atualizar o pacote e esquecer PrintBee/GuardLine

**Sintoma (antes):** `npm install -g` / `orchestrator update` no bootstrap atualizava só aquele workspace; consumidores ficavam em VERSION antiga.

**Comportamento (0.4.20):** update no workspace do pacote registra o path e propaga para todos em `%LOCALAPPDATA%\StarFusion\orchestrator\projects.json` com VERSION atrás. Relatório em `.orchestrator/runtime/reports/propagate-update.json`.

```bash
orchestrator update --project D:/StarFusion/bootstrap-agents
orchestrator update --project D:/StarFusion/bootstrap-agents --discover   # acha novos
orchestrator update --project D:/StarFusion/bootstrap-agents --no-propagate
```

Override de testes: `ORCHESTRATOR_PROJECTS_REGISTRY`.

---

## 0.4.73 — "A task travou?" — como responder em um comando

**Sintoma:** `task status` mostra o mesmo estado há minutos, `updated_at` parece
congelado, e não há como saber se o processo morreu ou se a fase é longa.

**Causa:** duas coisas conspiram. `updated_at` **só muda em transição de
estado** — um executor legítimo passa 25 min em `EXECUTING` sem tocá-lo (é o
bug-096). E até a 0.4.72 o único sinal de vida era o `agent_progress`, que só
existe **enquanto um CLI está no ar**: nos vãos (escolha de agentes,
consolidação, gravação de memória, gate de documentação, troca de etapa) o
runtime ficava mudo de verdade.

**Comportamento (0.4.73):** o loop bate a cada 20–30 s durante toda a execução,
e o `status` responde direto:

```bash
orchestrator task status <task_id> --text
```

```
8e4329205f01 EXECUTING
[VIVO] EXECUTING há 412s — codex/executor no ar (pid=50764) | sinal há 8s | pid=50764 vivo
```

No JSON é o bloco `live`:

```json
{"live": {"signal": "loop_progress", "signal_age_s": 8, "phase": "EXECUTING",
          "phase_elapsed_s": 412, "agent_active": true, "agent": "codex",
          "pid": 50764, "pid_alive": true}}
```

**Como ler:**

| O que aparece | O que significa |
|---|---|
| `signal_age_s` menor que ~60 e `pid_alive: true` | trabalhando; **não cancele** |
| `agent_active: true` | um CLI está rodando — `phase_elapsed_s` grande é normal |
| `agent_active: false` | entre etapas (consolidação, memória, docs); o loop segue vivo |
| `signal_age_s` grande **e** `pid_alive: false` | o processo dono morreu; o reaper vai cancelar |
| `pid_alive: true` com sinal antigo | processo vivo e loop parado — caso raro, vale `task logs` |

Para acompanhar ao vivo, `orchestrator run` já imprime cada batida no stderr:

```
[loop_progress] EXECUTING há 412s — codex/executor no ar (pid=50764)
[loop_progress] CONSOLIDATING há 12s — entre etapas, nenhum agente no ar (última: claude/validator)
```

> **O reaper ignora essa batida de propósito.** Ela nasce de uma thread do
> processo dono e continuaria batendo com o loop travado num lock — contá-la como
> progresso trocaria a fila parada de 11 h do bug-090 por uma eterna. Ela prova
> que o **processo** vive, não que o trabalho anda. Fase longa e legítima **sem
> agente no ar** continua sujeita ao reaper como antes.

---

## 0.4.72 — Agente sai em 0 s com `exit=3221225794` e a reinstalação também falha

**Sintoma:** `task logs` mostra o agente morrendo instantaneamente, sem escrever
byte nenhum, e o reparo automático falhando com o mesmo código:

```
corrector/codex     exit=3221225794  0s  stdout=0  stderr=0
agent_repair: codex: reinstalação falhou (exit=3221225794)  repair_ok: false
```

**Causa (bug-109):** `3221225794` é `0xC0000142` (**STATUS_DLL_INIT_FAILED**) — o
processo não conseguiu nem inicializar. A máquina estava sem recurso para criar
processos (memória, desktop heap, limite de handles). Como um processo que não
nasce não imprime nada, o classificador caía na regra do fast-fail mudo e
devolvia `install`, disparando uma reinstalação que **também não conseguia
nascer**.

O sinal decisivo é esse: **se o próprio reparo falha com o mesmo exit code, o
problema não é o CLI.**

**Comportamento (0.4.72):** categoria `launch`, avaliada antes de qualquer
marcador. Não reinstala, e a degradação fala de máquina:

```json
{"kind": "agent_launch_failed",
 "detail": "o processo não chegou a iniciar (exit=3221225794, papel corrector) — falta de recurso da máquina, não do CLI",
 "action": "libere memória/processos na máquina (ou reinicie) e reexecute; não há o que instalar nem logar"}
```

**O que fazer:** feche o que estiver pesando na máquina (suítes de teste,
builds, muitos agentes em paralelo) e reexecute. Se acontecer com a máquina
ociosa, é sinal de esgotamento real de recurso do sistema — vale olhar memória
livre e limites de processo.

> **Escopo estreito.** Só a família de falta de recurso
> (`0xC0000142`, `0xC0000017`, `0xC000012D`, `0xC0000018`) conta como `launch`.
> Access violation (`0xC0000005`) e stack overrun (`0xC0000409`) ficam de fora
> de propósito: são crash de binário, onde reinstalar pode de fato resolver.

---

## 0.4.71 — `orchestrator run` recusa `--prompt`

**Sintoma:**

```
$ orchestrator run --prompt "..."
Usage: run [OPTIONS] {service} {json_out}
Error: No such option: --prompt
```

**Causa (bug-108):** entre a 0.4.66 e a 0.4.70, o helper interno `_drain_queue`
ficou logo abaixo do `@app.command("run")` e **engoliu o decorator**. O `typer`
registrou o helper como o comando `run` — daí os parâmetros internos `service` e
`json_out` no `Usage` — e o `run_cmd` real ficou órfão.

**Correção:** atualizar para 0.4.71.

**Como verificar** — e aqui há uma pegadinha. Não use `version --json`:

```bash
orchestrator run --help
```

Tem que aparecer `Usage: ... run [OPTIONS]` com `--prompt ... [required]`. Se
aparecer `{service} {json_out}`, o processo ainda está com o módulo antigo.

> **O `code_fingerprint` não cobre o CLI.** `_FINGERPRINT_FILES` lista os
> arquivos que mudam o comportamento observável do **MCP** — `cli.py` não está
> lá, de propósito: incluí-lo faria o MCP se declarar `modules_stale` a cada
> mexida no CLI e o gate de `mcp_stale_run_reject` (0.4.24) passaria a recusar
> execuções sem motivo. Então `sha256_16 == disk_sha256_16` **não** prova que o
> CLI está atualizado. Para o MCP, `version --json` continua sendo a checagem
> certa; para a superfície do CLI, é `--help`.

**Depois de atualizar, recarregue o servidor MCP.** Um processo longo-lived
mantém os módulos antigos em memória e segue se comportando como a versão velha,
mesmo com o disco correto.

---

## 0.4.71 — Task COMPLETED com score 1.0 e nada entregue

**Sintoma:** `task status` mostra `COMPLETED` com `score=1.0`, mas nenhum arquivo
mudou. Em alguns casos o `task logs` tem uma validação **rejeitada** antes disso,
e `validation_rounds` guarda `rejected score=0.1`.

**Causa (bug-107):** a task encerrou pelo outcome `premise_mismatch` — o executor
declarou que a premissa estava incorreta. O outcome é legítimo, mas o runtime
gravava `last_score = 1.0` e `success=True` **sem validator nenhum**, e honrava a
alegação mesmo depois de uma rejeição registrada. Dá para reconhecer pela
transição:

```
EXECUTING -> COMPLETED   reason: premise_mismatch
```

**Comportamento (0.4.71):**

| situação | resultado |
|---|---|
| alegação na 1ª passada | `COMPLETED`, `last_score = null`, degradação `premise_declared_unverified` |
| alegação após rejeição gravada | `INCOMPLETE`, motivo `premise_mismatch_after_rejection` |

Para saber se a task entregou algo, leia as `degradations` — não o status
sozinho. `premise_declared_unverified` significa **nada foi entregue**.

> **Limitação conhecida.** O caminho legítimo continua marcado `COMPLETED`, que
> em `task list` é indistinguível de entrega. Um estado terminal próprio mexeria
> na state machine e em todos os clientes.

---

## 0.4.70 — Agente é reinstalado toda vez e continua falhando igual

**Sintoma:** `task logs` mostra `agent_repair` com
`CLI parece quebrado; tentando reinstalar` → `repair_ok: true`, e o mesmo agente
falha de novo na chamada seguinte, do mesmo jeito. O CLI funciona quando você o
roda à mão.

**Causa (bug-106):** quem falhou foi o **serviço do provedor**, não o CLI. O
classificador só tinha `install` e `auth`; erro de servidor não casa com marcador
nenhum e caía na regra final (stdout vazio + morte rápida) como `install`.
Assinatura típica — `exit=1` em ~2 s com poucas centenas de bytes:

```
Error: {"name":"UnknownError","data":{"message":"Unexpected server error.
Check server logs for details.","ref":"err_da9ff4ff"}}
```

**Comportamento (0.4.70):** categoria `service`, avaliada antes de `auth` e
`install`. O runtime **não reinstala**, registra o evento e sobe a degradação:

```json
{"kind": "agent_service_down",
 "impact": "opencode não pôde trabalhar",
 "action": "nada a instalar nem logar — tente de novo mais tarde ou troque o agente deste papel"}
```

As três categorias existem porque os remédios são **opostos**: reinstalar apaga
a sessão de quem só precisava logar, e logar não conserta um servidor fora do ar.

> **Limitação conhecida.** A quarentena de agente (bug-070) exige 3 falhas **por
> projeto**, e o banco é por projeto. Uma queda de provedor que afeta a conta
> inteira é redescoberta em cada repositório.

---

## 0.4.70 — Task cancelada pelo reaper, mas a validação já tinha aprovado

**Sintoma:** `task status` mostra `CANCELLED` com
`auto-cancel: ... sem sinal de vida há Ns`, e o `task logs` mostra o validator
tendo respondido `{"status":"accepted","score":1.0}` **antes** disso, com
`exit=0`.

**Causa (bug-105):** duas coisas na mesma mensagem.

1. O número da idade era escrito como se fosse tempo de fase. `VALIDATING há
   4525s` na verdade dizia "a **task** tem 4525 s"; em `VALIDATING` ela estava
   há 2963 s. Terceira reincidência (bug-093, bug-096).
2. O reaper descartava a task **sem dizer o que ela já tinha conquistado**. O
   veredito aprovado estava gravado em `validation_rounds` e o dono lia só
   "cancelada" — e refazia do zero um trabalho já aceito.

**Comportamento (0.4.70):** a mensagem nomeia o relógio e carrega o que se
perdeu:

```
auto-cancel: em VALIDATING, criada há 4525s e sem sinal de vida há 2423s
(> maximum_duration_seconds + 900s) | ATENÇÃO: a última validação já havia
APROVADO (score=1.0) — o trabalho existe, só não foi consolidado
```

A **decisão** não muda: sem processo dono vivo não dá para consolidar a task com
honestidade. O que muda é você saber que o diff está lá antes de mandar refazer.

> **Limitação conhecida.** Entre um agente e outro o runtime não emite sinal de
> vida — o heartbeat de 30 s existe só enquanto um CLI está rodando. Morte de
> processo e fase longa sem agente são, hoje, indistinguíveis para o reaper.

---

## 0.4.70 — Só as tarefas GRANDES falham, sempre no validator

**Sintoma:** `task status` mostra `FAILED` com

```
Orçamento de tempo insuficiente para validator (timeout_s=0)
```

Tarefas curtas passam; as longas morrem. Parece que o orquestrador "não aguenta"
trabalho grande — e a mensagem parece falha de mérito.

**Causa (bug-104):** aritmética, não azar. Uma volta com correção soma os tetos
dos papéis:

```
planner 900 + executor 2400 + tester 600 + validator 1200
             + corrector 2400 + validator 1200 = 8700s
```

contra um `maximum_duration_seconds` de **3600**. O orçamento era **conferido no
topo da iteração** mas **gasto dentro dela**: executor e corrector consumiam o
teto inteiro e o validator — o **último** a ser chamado — chegava com
`timeout_s=0`. Por isso a morte caía sempre nele, e por isso só as tasks que
realmente usavam o orçamento morriam. A incoerência estava documentada desde a
0.4.60 (a nota "2400 + 2400 > 3600" logo abaixo) e nunca tinha sido corrigida.

**Comportamento (0.4.70):** três defesas.

1. **Piso derivado.** `maximum_duration_seconds` nunca fica abaixo da soma dos
   `agent_timeout_by_role` naquele percurso. Vale ao **carregar** a configuração,
   então projetos com 3600 no `policies.json` são corrigidos sem editar nada; o
   valor pedido fica em `duration_floor_raised_from`.
2. **Reserva do veredito.** `executor` e `corrector` devolvem 600 s do restante
   para o julgamento — sem nunca cair abaixo do mínimo de invocação.
3. **Degradação honesta.** Sem orçamento, o veredito determinístico assume e o
   resultado registra `validation_not_independent` com o remédio certo, em vez de
   estourar.

Teto é limite de **paciência**, não de qualidade: subir não faz task nenhuma
demorar mais, só para de matar as que ainda estavam trabalhando. Para dar mais
de uma correção, suba explicitamente:

```json
{ "maximum_duration_seconds": 10800 }
```

---

## 0.4.63 — Task parada há horas e nenhum timeout dispara

**Sintoma:** `task status` fica no mesmo estado (`PLANNING`, `EXECUTING`) por 40
min ou mais. Nenhum timeout de papel dispara, o watchdog de silêncio da 0.4.60
não mata ninguém, `task logs` não cresce, e o `workspace.write.lock` continua
com o PID do processo vivo. Não há erro em lugar nenhum — a task simplesmente
não anda.

**Causa (bug-090):** `CliExecutor.run` escrevia o `stdin` **antes** de subir as
threads leitoras de `stdout`/`stderr`. Prompt grande vai por stdin (acima do
teto de argv, `agents/base_adapters.py:172`) e trava dos dois lados: o pai enche
o buffer de entrada (~64 KB no Windows) e espera o filho consumir; o filho enche
o de saída e espera alguém ler — e as leitoras ainda nem existiam. Como
`proc.wait(timeout=...)` só vem **depois** dessa escrita, nenhum teto se
aplicava: nem o do papel, nem o `agent_no_output_timeout_s`, nem o teto da task.

**Como confirmar:**

```bash
orchestrator task status <task_id>   # mesmo estado, updated_at antigo
orchestrator version --json          # fingerprint + features do runtime
```

Se `stdin_written_after_readers` **não** estiver na lista `features` de
`orchestrator version --json`, o runtime é anterior à 0.4.63 e ainda tem o
deadlock — rode `orchestrator update`. Com a task travada em aberto, o processo
Python aparece vivo e sem CPU, e o prompt (`orchestrator task list --json`, que
traz o prompt integral) passa dos ~64 KB. Em
`.orchestrator/runtime/results/<task-id>/` você vê a outra ponta do deadlock:
os arquivos `<papel>-<agente>.txt` guardam a **saída** do agente, e nesse
cenário eles ficam vazios ou nem chegam a existir. A partir da 0.4.63 a escrita
do stdin é thread própria, iniciada **depois** das leitoras
(`agents/process.py:386-411`).

---

## 0.4.63 — Fila inteira em QUEUED atrás de uma task que nunca termina

**Sintoma:** toda task nova entra em `QUEUED behind <id>` e nunca sai. O `<id>`
que bloqueia está em `EXECUTING`/`PLANNING` há horas, não é terminal, e nenhum
processo do orquestrador está de fato trabalhando nele — medido: ~11 h de fila
parada no printbee.

**Causa (bug-093):** só existia reaper de task `RECEIVED`
(`_cancel_stale_received`). Task presa em estado não-terminal ficava para
sempre; `_busy_task_id` seguia devolvendo ela e o gate de fila mandava todo
mundo esperar. Qualquer morte fora do caminho feliz produzia isso — processo MCP
derrubado, máquina reiniciada, kill manual — inclusive depois do bug-090
corrigido.

**Como confirmar:**

```bash
orchestrator task list                 # a bloqueadora não-terminal e a fila atrás dela
orchestrator task status <bloqueadora> # updated_at parado
```

Confira também `.orchestrator/runtime/locks/workspace.write.lock`: o arquivo
carrega `{"pid", "ts"}`; se o PID não existe mais, ninguém está segurando o
workspace.

**Comportamento (0.4.63):** `_cancel_stale_execution()` só olha para task
não-terminal **parada há pelo menos `stale_execution_grace_s`** — mais nova que
isso é jovem demais para julgar e é ignorada, mesmo que ninguém segure o lock.
Passada a folga, ela é cancelada em dois casos: `updated_at` além de
`maximum_duration_seconds + stale_execution_grace_s`, **ou** nenhum processo
vivo segurando o lock do workspace. Não existe cancelamento imediato só porque o
lock ficou sem dono. Cancelada, o runtime desfila a próxima. Task que **este**
processo está rodando nunca é ceifada; `QUEUED` fica de fora de propósito —
esperar é o trabalho dela, quem a destrava é o cancelamento de quem está na
frente. Roda no `create`/`status`/`list`, então basta consultar.

```json
{ "stale_execution_grace_s": 900 }
```

`0` desliga o reaper. Feature: `stale_execution_reaper`.

---

## 0.4.63 — Chamada MCP muda por 1800 s com a task já rodando

**Sintoma:** `orchestrator_run` não responde e o cliente MCP fica pendurado até
o teto de 1800 s, **enquanto** a task aparece rodando normalmente em
`orchestrator task list` num outro terminal. Cancelar no chat não adianta: a
task já foi disparada, quem travou foi a resposta.

**Causa (bug-094a):** `_npm_global_bins_nt()` usava
`subprocess.run(capture_output=True, timeout=15)`. No Windows, quando esse
timeout estoura, o `communicate()` pós-kill espera **todo neto** que herdou o
handle do pipe — é o bug-059, corrigido em `git_workspace._run_git` e nunca
aplicado aqui. Esse caminho roda dentro de `which()` → `detect()`, que
`orchestrator_run` chama **depois** de já ter criado e disparado a task.

**Como confirmar:** com a chamada pendurada, procure um `npm.cmd`/`node` órfão
na árvore do processo MCP (`Get-Process npm,node`) enquanto
`orchestrator task status <id>` responde normal pela CLI. É a assinatura: task
viva, resposta morta.

**Comportamento (0.4.63):** captura por **arquivo temporário**, nunca por PIPE
(`run_capture_file`, `agents/process.py:506`): `Popen` + arquivo + `taskkill /T`
no timeout. Deadlock de EOF fica impossível e a árvore inteira morre junto.
Devolve `124` no timeout e `127` quando nem executou.

---

## 0.4.63 — CLI de agente sai `exit=1` com zero byte

**Sintoma:** o agente termina em segundos com `exit=1`, `stdout=0B stderr=0B`, e
a task queima iteração atrás de iteração. Observado com `codex` e `opencode`,
como executor **e** como validator, em mais de um projeto (task `143e8b2ca47b`:
quem salvou foi o corrector `claude/opus`). Até a 0.4.62 o agente só entrava em
quarentena (bug-070) — o sintoma sumia da vista sem nada ter sido consertado.

**Causa:** o CLI do agente está quebrado (instalação corrompida, módulo ausente,
versão sem suporte) **ou** sem credencial. Os dois se parecem no log e pedem
remédios opostos: reinstalar um CLI que só está deslogado apaga a sessão e não
conserta nada.

**Como confirmar:**

```bash
orchestrator task logs <task_id>     # procure exit=1 com stdout/stderr vazios
codex --version                      # teste o CLI fora do orquestrador
```

Nos eventos da task procure `agent_repair` (`orchestrator_events`): ele traz
`failure_kind` (`install` ou `auth`), e no caso `auth` o comando de login a
rodar. Feature: `agent_broken_cli_detection`.

Ausência do evento **não** significa que o runtime não detectou nada: o caso
`auth` sempre reporta, mas o caso `install` só emite evento quando o reparo vai
de fato ser tentado. Com `agent_auto_repair: false`, ou quando aquele agente já
foi reparado antes **neste mesmo processo**, o runtime devolve o resultado do
agente em silêncio, sem evento. Se você desligou o auto-reparo, confie no
`task logs` (`exit=1` com saída vazia), não no evento.

**Comportamento (0.4.63):** `agents/health.py` classifica a falha em
`install` / `auth` / nenhuma, e `agents/repair.py` reinstala **uma vez por
agente por processo**, delegando a `scripts/Update-Agents.ps1 -Only <agente>` —
que já tem os mapas curados (npm/chocolatey/scoop/instalador nativo). Falta de
credencial **não** reinstala: o runtime emite o comando de login e para por aí.
Se a reinstalação der certo, o agente é executado de novo na hora.

```json
{ "agent_auto_repair": true, "agent_repair_timeout_s": 300 }
```

`agent_auto_repair: false` desliga a reinstalação: falha classificada como
`install` volta como está, **sem** evento `agent_repair` e sem nenhuma tentativa
— a chave desliga o caminho inteiro, diagnóstico incluído. O caso `auth`
continua reportando, porque ali nunca houve reinstalação a desligar. Host sem
PowerShell não é erro: o reparo se declara indisponível (`repair_available:
false` no evento) e a task segue.

**Nota importante:** `timed_out` **nunca** é classificado como CLI quebrado —
quem passou do tempo estava vivo, e esse caminho tem dono em `_timeout_issue`.
Sem nenhum marcador no log, só arrisca `install` quando o agente morreu **mudo e
rápido** (stdout vazio e duração < 90 s). Agente que rodou 17 min e escreveu
20 KB de stderr é mérito, não infraestrutura.

---

## 0.4.60 — Task gasta 1h e termina INCOMPLETE sem entregar nada

**Sintoma:** `task status` mostra INCOMPLETE com
`AGENT-TIMEOUT-NO-OUTPUT` e o log tem um agente com `stdout=0B stderr=0B` por
dezenas de minutos. O agente seguinte (corrector) morre pouco depois, mesmo
tendo produzido saída.

**Causa (bug-086):** não havia teto para "agente pendurado". O único limite era
o timeout do papel (`executor`/`corrector` = 2400s), pago inteiro por um
processo que nunca escreveu um byte. Como o teto da *task*
(`maximum_duration_seconds`) é 3600s, o silêncio consumia o orçamento do agente
seguinte — que era morto trabalhando. A configuração é incoerente por
construção: 2400 + 2400 > 3600.

**Comportamento (0.4.60):** watchdog mata o agente que passa
`agent_no_output_timeout_s` (padrão 900s) **sem nenhuma saída E sem tocar no
workspace**. As duas condições importam: `claude -p` só imprime no fim, então
silêncio sozinho não prova travamento.

```json
{ "agent_no_output_timeout_s": 900 }
```

`0` desliga. Se o seu executor legitimamente fica >15 min mudo **e** sem
escrever arquivo, aumente — não desligue.

**Rótulos (bug-087):** o erro agora diz qual morte foi, e cada uma tem remédio
diferente:

| Rótulo | Significa | Remédio |
|---|---|---|
| `AGENT-NO-OUTPUT-HANG` | pendurado, morto pelo watchdog | trocar de agente/modelo |
| `TASK-BUDGET-EXHAUSTED` | cortado pelo teto da task, não pelo papel | subir `maximum_duration_seconds` |
| `AGENT-TIMEOUT-NO-CHANGES` | falou mas não alterou arquivo | mérito, não infra: revisar prompt |
| `AGENT-TIMEOUT-NO-OUTPUT` | silêncio real dentro do timeout do papel | investigar o CLI |

---

## 0.4.60 — Task fica em RECEIVED com o workspace livre

**Sintoma:** `task list` mostra uma task RECEIVED parada há dezenas de minutos.
Não há lock, não há outra task rodando, e a fila não anda.

**Causa (bug-085):** o dequeue só olhava a fila `QUEUED`. Task criada por um
processo que morreu antes de rodar o loop — cliente MCP recém-instalado que
ainda não recarregou, CLI interrompido no meio do `create` — ficava órfã até o
auto-cancel de 6h, que resolvia o zumbi jogando o trabalho fora. Medido na
trustsafe: criada 23:02, primeiro agente às 23:33.

**Comportamento (0.4.60):** qualquer processo vivo do orquestrador adota a
órfã, inclusive no poll de `status`/`list` — então
`orchestrator task status <id>` destrava. Janela configurável:

```json
{ "orphan_received_adopt_after_s": 120 }
```

A janela existe para não roubar a task de quem acabou de criá-la e vai rodá-la
em seguida. `0` desliga a adoção.

---

## 0.4.19 — Duas tasks no mesmo projeto ao mesmo tempo

**Sintoma (antes):** segunda `orchestrator_run` competia pelo WriteLock, ficava `RECEIVED` com `blocked_by_lock` ou parecia travada; chat cancelava.

**Comportamento (0.4.19):** 1 execução ativa por `project_path`. Nova submissão → status `QUEUED`, campos `queue_position` e `blocked_by`. Ao terminar/cancelar a ativa, a próxima da fila inicia sozinha (FIFO). Projetos diferentes não se bloqueiam.

**Poll:** `orchestrator_status` mostra `Estado: QUEUED | fila pos=N blocked_by=<id>`.

## 0.4.16 — Tasks RECEIVED que nunca iniciam (zumbis de sessão anterior)

**Sintoma:** `orchestrator task list` mostra tasks RECEIVED antigas que nunca transitaram para ANALYZING. O chat tentou rodar mas a sessão foi perdida antes do dispatch.

**Causa:** Tasks RECEIVED sem lock ficam "mudas" — o processo que devia executá-las morreu. O orquestrador não as cancela automaticamente (antes de 0.4.16).

**Solução (0.4.16):** Auto-cancel de tasks RECEIVED com idade > `stale_received_ttl_hours` (padrão: 6h). Disparado automaticamente em `create_task`. Configurável em `policies.json`:

```json
{ "stale_received_ttl_hours": 6 }
```

---

## 0.4.16 — Task classificada incorretamente como "docs"

**Sintoma:** Prompt de implementação (ex.: "Criar/atualizar regras de produção") é classificado como `docs`, gerando ACs de evidência/análise em vez de workspace_changes.

**Causa:** O check de "doc" era substring, podendo casar falsamente em outros contextos. Além disso, prompts com intent de implementação E keyword "doc"/"documentação" ficavam presos como "docs".

**Solução (0.4.16):** Check usa `\bdoc` (word-boundary); prompts com verbo de implementação + keyword docs são promovidos para `implementation` (mesmo padrão do `complex_analysis`).

---

## 0.4.16 — `InvalidTransitionError: RETRIEVING_MEMORY -> RETRIEVING_MEMORY` (double-resume/MCP retry)

**Sintoma:** Task transita para FAILED com mensagem `Transição inválida: RETRIEVING_MEMORY -> RETRIEVING_MEMORY`. Ocorre quando o MCP faz retry de `orchestrator_run` ou quando o resume é chamado duas vezes na mesma task.

**Causa:** `assert_transition` não era idempotente — mesmo estado levantava `InvalidTransitionError`.

**Solução (0.4.16):** `assert_transition(same, same)` é no-op; `repo.transition(task, same_state, ...)` retorna sem salvar nem emitir evento.

---

## 0.4.16 — Duas tasks paralelas competem pelo workspace (PrintBee: 2 tabs simultâneos)

**Sintoma:** Uma das tasks completa normalmente; a outra trava em RECEIVED ou aparece com `error: Lock em uso por outra task asyncio`. Em versões anteriores a segunda task entrava no loop como se tivesse o lock (reentrância incorreta).

**Causa:** `WriteLock.acquire()` permitia a segunda task asyncio reentrar via `_depth` quando `_held=True`, pois não rastreava qual task asyncio detinha o lock. Spinning no event loop causaria deadlock.

**Solução (0.4.16):** `WriteLock` rastreia `_owner_task` (asyncio Task). Segunda task ≠ owner → `TimeoutError` imediato → `run_task` registra `blocked_by_lock` e retorna sem FAILED na task em andamento.

---

## One-liner / CLI npm

### Acentos somem ou viram `�` / `?` no Cursor ou PowerShell

**Sintoma:** `correção` aparece como `correo`/`corre��o`, `botões` como `botes`/`bot�es`, ou a descrição termina no meio de uma palavra.

**Causa até 0.4.6:** o Python herdava CP1252 em pipes Windows e a CLI emitia bytes CP1252; consumidores Cursor/Node os decodificavam como UTF-8. Além disso, `task list` cortava o prompt silenciosamente em 60 caracteres. A entrada MCP e o SQLite não alteravam o texto.

**Solução:**

1. Atualize o pacote/runtime para 0.4.7 ou superior.
2. Reinicie o MCP/recarregue a janela do Cursor para descartar o processo antigo.
3. Use `orchestrator task list --json` quando precisar do prompt integral; a saída texto é um preview explícito com `…`.

Registros antigos não exigem migração se o prompt armazenado no SQLite estiver correto; o defeito era na saída. O runtime 0.4.7 fixa UTF-8 nos streams antes de Typer/FastMCP escreverem.

---

### `npx` pede autenticação ou falha no clone

**Causa:** repositório privado sem credencial Git configurada.

**Solução:**

1. `gh auth login` (HTTPS ou SSH)
2. Confirme `git ls-remote https://github.com/henrique-starfusion/orchestrator-ia.git`
3. Repita: `npx --yes github:henrique-starfusion/orchestrator-ia#latest init`

---

### `PowerShell nao encontrado` (CLI Node)

**Causa:** `bin/orchestrator.js` não achou `powershell.exe` / `pwsh`.

**Solução:** use Windows PowerShell 5.1+ ou instale PowerShell 7 e garanta que estejam no PATH.

---

### `gh api ... | iex` falha com 404 / Bad credentials

**Causa:** sem login no GitHub CLI, branch inexistente ou token sem escopo `repo`.

**Solução:**

```powershell
gh auth status
gh auth refresh -s repo
gh api repos/henrique-starfusion/orchestrator-ia --jq .full_name
```

---

### Cache corrompido após `get.ps1`

**Causa:** clone incompleto em `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator`.

**Solução:**

```powershell
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\StarFusion\multiagent-orchestrator"
# rode o one-liner novamente, ou:
.\get.ps1 -ForceRefresh
```

---

### `orchestrator` / `mao` não reconhecido após npm global

**Causa:** pasta de bins do npm fora do PATH.

**Solução:**

```bash
npm prefix -g
npm bin -g
# adicione o caminho de bin ao PATH e reabra o terminal
npm install -g github:henrique-starfusion/orchestrator-ia#latest
```

---

## Erros de preflight (Detect-Environment)

### `PowerShell 5.1 ou superior e obrigatorio`

**Causa:** versão antiga do PowerShell.

**Solução:** use Windows PowerShell 5.1+ ou PowerShell 7+ (`powershell.exe` invocado pelo BAT).

---

### `git nao encontrado no PATH`

**Causa:** Git não instalado ou fora do PATH.

**Solução:** instale [Git for Windows](https://git-scm.com/) e reinicie o terminal.

---

### `Integridade do pacote`

**Causa:** arquivos ausentes em `package/` (manifest, template, sources).

**Solução:**

- Confirme clone/cópia completa do repositório orchestrator-ia
- Se veio via npm/npx, reinstale o pacote (`npx` limpa cache com `--yes` / limpe npm cache se necessário)
- Se veio via `get.ps1`, force refresh do cache (`-ForceRefresh`)
- Verifique `package/manifest.json` e `package/template/.orchestrator/`
- Não edite `checksums.json` manualmente sem regenerar

---

### `Sem permissao de escrita no projeto`

**Causa:** ACL, pasta somente leitura ou projeto em local protegido.

**Solução:** execute em diretório gravável ou ajuste permissões NTFS.

---

### `Espaco livre insuficiente`

**Causa:** menos de 50 MB livres no volume do projeto.

**Solução:** libere espaço em disco.

---

### `Lock de instalacao ja existe`

**Causa:** arquivo `.orchestrator/runtime/install.lock` presente.

**Solução:**

1. Confirme que nenhum `install` está em execução
2. Se lock órfão, remova manualmente `install.lock`
3. Reexecute o comando

---

## Erros de versão

### `Workspace mais novo que o pacote` (exit 6)

**Causa:** `.orchestrator/VERSION` > `VERSION` na raiz do pacote orchestrator-ia.

**Solução:**

- Atualize o pacote orchestrator-ia para versão ≥ workspace
- **Não** force downgrade sem backup

---

### `Comparacao de versao invalida` (upgrade)

**Causa:** VERSION malformado (não semver).

**Solução:** corrija `.orchestrator/VERSION` para formato `MAJOR.MINOR.PATCH` ou use `-Force` conscientemente.

---

## Erros de validação

### `.orchestrator ausente`

**Solução:**

```bat
orchestrator-ia.bat install -ProjectPath C:\dev\projeto
```

---

### `Arquivo gerenciado ausente`

**Causa:** remoção manual de arquivos do manifest (modo `managed`).

**Solução:**

```bat
orchestrator-ia.bat repair -ProjectPath C:\dev\projeto
```

---

### `JSON invalido` em config ou registry

**Causa:** edição manual corrompeu JSON.

**Solução:**

1. Identifique o arquivo no log de validação
2. Restaure de `.orchestrator/backups/` ou git
3. Rode `repair` se necessário

---

## Agentes

### Codex trava em VALIDATING / processo fica preso por 10–20 min no Windows

**Sintoma A (sandbox 740):** tarefa fica em VALIDATING/EXECUTING; log com `CreateProcessAsUserW failed: 740` / `windows sandbox: runner failed`.

**Sintoma B (subagentes / printbee-patterns, 0.4.18):** sandbox já é `danger-full-access`, mas o log cresce para MB com `collab: Wait`, `command timed out after 124`, menções a “três subagentes” / `printbee-patterns`. O Codex entra em loop de wait em vez de implementar inline.

**Causa:** o profile padrão do Codex usa `--sandbox workspace-write`, que no Windows exige que `CreateProcessAsUserW` crie um processo restrito — operação que requer elevação de privilégio (erro 740 = `ERROR_ELEVATION_REQUIRED`). O Codex **não aborta** ao receber esse erro; em vez disso, tenta novamente via MCP `node_repl/js` indefinidamente.

Mecanismos:

1. **Override sandbox Windows (0.4.15):** `workspace-write` → `danger-full-access` em `os.name == "nt"`.
2. **Fail-fast 740 (0.4.15):** após N marcadores 740 no stream, mata o processo (`agent_infra_fail_fast_count`).
3. **Restrição child always-on (0.4.18):** prompt do executor/validator/planner **sempre** proíbe spawn/collab/Wait e ignora rito de N subagentes (não depende mais da env no processo MCP).
4. **Fail-fast collab (0.4.18):** marcadores `collab: wait` e `command timed out after 124` também disparam INFRA-FAIL-FAST.

**Solução (em caso de install anterior a 0.4.15):**

```bash
orchestrator update --force
```

**Verificação:**

```bash
# Confirme que o runtime é 0.4.15+:
orchestrator status
# Deve listar features: codex_infra_failfast, codex_sandbox_windows_override
```

**Ajuste de sensibilidade** (se 3 for alto/baixo demais):

```json
# .orchestrator/config/policies.json
{ "agent_infra_fail_fast_count": 2 }
```

**Nota:** o erro 740 não é um problema de mérito — o agente simplesmente não consegue inicializar o sandbox. O runtime trata isso como `validator_infra_failure` e nunca converte em rejeição de AC.

---

### Nenhum agente detectado

**Causa:** CLIs não estão no PATH.

**Solução:**

1. Instale o CLI desejado (ex.: Claude Code, Codex)
2. Abra novo terminal
3. `orchestrator-ia.bat analyze -ProjectPath ...`

Registro: `.orchestrator/agents/detected.json`

---

### Agente `installed_failed`

**Causa:** binário encontrado, mas `--version` falhou ou timeout.

**Solução:** teste manualmente no terminal (`claude --version`, etc.). Reinstale o CLI se corrompido.

---

### Adaptador não criado

**Causa:** agente detectado sem template de adaptador (ex.: `aider`, `goose`).

**Solução:** normal — só vendors mapeados recebem adaptador. Config canônica ainda funciona via `.orchestrator/`.

---

### Update de CLIs de agentes falhou

**Causa:** `claude|codex|kimi update`, `npm install -g`, `choco upgrade` ou `scoop update` retornou erro.

**Solução:** avisos não bloqueiam install/update. Veja `.orchestrator/runtime/reports/agent-updates.json`. Atualize o CLI manualmente ou use `-SkipAgentUpdates` / `--skip-agent-updates` para pular a etapa.

---

## Ferramentas opcionais

### `OpenWolf nao encontrado` / `Graphify nao encontrado`

**Esperado** se não instalados. Não bloqueia install.

**Solução (opcional):** instale as ferramentas e reexecute install ou `analyze`.

Use `-SkipTools` para suprimir a etapa.

---

### `uv tool upgrade graphifyy falhou`

**Causa:** Graphify não instalado via uv ou nome de pacote indisponível.

**Solução:** aviso apenas. Instale Graphify manualmente se necessário.

---

## MCP

### Context7 não conecta

**Causa:** registrado com `enabled: false` por padrão.

**Solução:** edite `.orchestrator/mcp/registry.json`, defina `enabled: true` após configurar credenciais/ambiente.

---

## Migração legada

### Conteúdo duplicado após migração

**Causa:** `.claude/memory` importado para `legacy-import/` enquanto `.claude/` permanece.

**Solução:** consolide manualmente em `.orchestrator/memory/` e documente decisões em `memory/decisions/`.

Veja [`legacy-migration.md`](legacy-migration.md).

---

## Uninstall

### Arquivos adaptadores permanecem

**Esperado:** `uninstall` remove entradas do manifest em `.orchestrator/`, não `CLAUDE.md` ou `.cursor/` na raiz.

**Solução:** remova adaptadores manualmente se desejar.

---

### `-Force` remove tudo

**Causa:** `-Force` no uninstall apaga `.orchestrator/` inteiro.

**Solução:** sempre revise backup em `.orchestrator/backups/*-pre-uninstall/` antes.

---

## Limpeza de legado e flags

Limpeza automática: [`legacy-cleanup.md`](legacy-cleanup.md).

| Flag / comando | Status |
|---|---|
| `--skip-legacy-cleanup` / `--legacy-cleanup-mode` | Implementado (0.4.0+) |
| `orchestrator legacy restore --backup <id>` | Implementado |
| `-InstallMissingAgents` | Não implementado |
| `-RunProjectTests` | Não implementado |

---

## Simulação (DryRun)

```bat
orchestrator-ia.bat install -ProjectPath C:\dev\projeto -DryRun
orchestrator-ia.bat upgrade -DryRun
```

Útil para preview sem lock nem escrita.

---

## Coleta de evidências para suporte

Inclua:

1. Saída completa do comando com erro
2. `orchestrator-ia.bat status -ProjectPath ...`
3. Último log em `.orchestrator/runtime/validations/`
4. `installation-report.md`
5. Versões: `VERSION` (pacote) e `.orchestrator/VERSION`

---

## MCP stale / run recusado (0.4.24+)

Sintoma: `orchestrator_run` retorna `status=FAILED` com `mcp_modules_stale` sem criar task.

Causa: o processo MCP ainda carrega código antigo (`modules_stale=true`).

Ação: recarregar o servidor MCP / reiniciar o Cursor. Emergência: `ORCHESTRATOR_ALLOW_STALE_MCP=1` (não recomendado).

## Cancel que “não para” / CANCELLED → TESTING (bug-022, 0.4.24+)

A partir de 0.4.24 o `save` não sobrescreve estado terminal e `transition` aborta com `CancelledError`. Use `orchestrator_cancel` com `reason` — o motivo fica em `error`.

## Registry com dezenas de Temp/orchestrator-tests

`Prune-OrchestratorProjectRegistry` (automático no propagate 0.4.24+) remove paths mortos e fixtures de teste. Install/update de fixtures não registra mais no registry global.

## Task reprova por critérios que ninguém pediu (bug-045/046, 0.4.35+)

Sintoma: validação rejeita com ACs de outro tipo de trabalho — ex. *"Defeito
reproduzido com evidência"* numa task de documentação/coleção Postman — até
`same_issue_repeat_limit` → INCOMPLETE.

Causa (até 0.4.34): `detect_loop` casava substring sem fronteira de palavra
("erro" dentro de "errors", "mvp" em "o MVP já existe", "se gap for bug" em
cláusula condicional) e o template do loop substituía critérios escritos no
prompt como "Critérios: a; b; c" (só `AC-001:` era reconhecido).

A partir de 0.4.35: palavra inteira, condicionais não contam, hit isolado em
prompt longo não impõe loop, e a seção "Critérios:" (prosa ou bullets) vira os
ACs da task com precedência sobre o loop. Dica: declarar critérios no prompt é
sempre o caminho mais confiável.

## `changed=[]` / `AGENT-TIMEOUT-NO-OUTPUT` com trabalho real feito (bug-047, 0.4.35+)

Sintoma: o executor trabalha (stderr mostra diffs), mas `changed_files` fica
vazio, `workspace_changes` nunca passa e timeout vira `AGENT-TIMEOUT-NO-OUTPUT`.

Causa: workspace é uma pasta-mãe contendo repos git **aninhados** (ex.:
`GuardLine.BR/travelex-api`, cada filho com `.git` próprio). `git status` na
raiz não desce em repo aninhado.

A partir de 0.4.35 o baseline captura o porcelain de cada repo filho imediato e
o diff reporta `filho/arquivo` — inclusive quando a raiz não é repo git. Só o
primeiro nível de aninhamento é observado. Em 0.4.36 a descoberta de testes
(bug-048) também passou a rodar nos repos filhos tocados — antes o `TESTING`
reportava `<none>/skipped` na raiz e o validador reprovava `tests_pass` por
falta de evidência.

## Prompt gravado com "Ã" no lugar de acentos (bug-049, 0.4.36+)

Sintoma: prompt aparece no DB/status como "exigÃªncia", "coleÃ§Ã£o".

Causa: terminal Windows com codepage CP1252 — o texto UTF-8 do comando chega
corrompido ao argv antes do orquestrador (observado com caller=cursor).

A partir de 0.4.36 a ingestão repara automaticamente (round-trip cp1252→utf-8
com guarda de assinatura; "NÃO"/"SÃO" legítimos passam intactos). Prevenção no
cliente: `chcp 65001` ou `[Console]::OutputEncoding = [Text.Encoding]::UTF8`.

## Janela de console pisca a cada commit (hook graphify) (bug-055, 0.4.39+)

Sintoma: a cada `git commit`/`git checkout`, uma janela de terminal
aparece/pisca — é o rebuild do grafo do graphify lançado via `python.exe`
(subsistema de console) sem supressão de janela.

A partir de 0.4.39, `orchestrator install/update/propagate` aplica reparo
idempotente nos hooks `post-commit`/`post-checkout` (raiz + repos filhos):
prefere `pythonw.exe` no interpretador pinado e adiciona `CREATE_NO_WINDOW`
ao Popen destacado. `graphify hook install` desfaz o fix — basta rodar
`orchestrator update` para reaplicar. Backups: `*.bak-orchestrator-*` ao lado
do hook.

## Agente recusa orquestrar: "sou filho" com var vazia (bug-057, 0.4.41+)

Sintoma: o agente principal diz que é delegado e faz tudo inline;
`ORCHESTRATOR_CHILD_AGENT` aparece no ambiente **vazia** (herdada de shell).

A partir de 0.4.41 a flag é por VALOR: vazio ou `0` não é filho — em runtime,
guard, Invoke-RoutedAgent e nos textos dos adapters. Só o valor `1` (setado
pelo runtime no processo delegado) identifica o filho.

## "PowerShell nao encontrado" em shell de agente (bug-058, 0.4.41+)

Sintoma: `orchestrator` falha porque o PATH do shell não tem System32.

A partir de 0.4.41 o CLI tenta também os caminhos absolutos
`%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` (e `Sysnative`).
Não é preciso mexer no PATH.

## Fila presa atrás de task CANCELLED (bug-059, 0.4.42+)

Sintoma: tasks novas ficam `QUEUED behind <id>` de uma task que já está
CANCELLED; `workspace.write.lock` antigo no disco com PID do processo MCP.

Causa (até 0.4.41): coroutine do pré-loop congelava num `git status` (PIPE +
neto do git herdando handles), nunca soltava lock/`_running_tasks`, e o gate
de fila apontava para a task terminal.

A partir de 0.4.42 o git roda sem possibilidade de deadlock, task terminal
nunca ocupa o workspace, cancel aborta o pré-loop e desfila a próxima. Se um
processo MCP antigo ainda estiver congelado: recarregar o Cursor/MCP e, se o
lock persistir, apagar `.orchestrator/runtime/locks/workspace.write.lock`.

## Agente não delega mesmo com o subagente instalado (bug-083, 0.4.59+)

Sintoma: `.claude/agents/orquestrador.md` existe, mas o Claude edita direto —
a thread principal é o agente genérico e só delega se "achar" que deve.

A partir de 0.4.59 o install/update grava o agente padrão da sessão:

| CLI | Arquivo | Chave |
|---|---|---|
| claude code | `.claude/settings.json` | `"agent": "orquestrador"` |
| opencode | `opencode.json` (raiz) | `"default_agent": "orquestrador"` |

No claude, a chave faz a main thread rodar **como** o subagente (herda system
prompt e tools restritas — sem write/edit). No opencode, `default_agent` exige
agente *primary*: por isso o subagente usa `mode: all`.

Se você definiu um `agent` próprio, o orquestrador **não sobrescreve** — emite
aviso. Para orquestrar por padrão, troque o valor para `orquestrador`.

Gemini CLI, codex e kimi code não têm chave equivalente (verificado na doc
oficial em 08/2026); neles o desvio vem do subagente + `AGENTS.md`.

## Ver também

- [`cli-reference.md`](cli-reference.md)
- [`installer-architecture.md`](installer-architecture.md)
- [`legacy-migration.md`](legacy-migration.md)
