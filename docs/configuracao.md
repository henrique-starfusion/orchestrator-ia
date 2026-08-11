# Configuração

Toda a configuração canônica vive em `.orchestrator/config/`. O runtime lê
**apenas três** desses arquivos: `policies.json`, `models.json` e
`manager_model.json` (`runtime/src/orchestrator_runtime/config.py:215-217`).

Caminhos derivados, na mesma função `load_config`:

| Caminho | Uso | Evidência |
|---|---|---|
| `.orchestrator/data/` | Diretório do banco; criado e, em Unix, com `chmod 0700` | `config.py:208-214` |
| `.orchestrator/data/orchestrator.db` | Banco SQLite | `config.py:295` |
| `.orchestrator/agents/profiles/` | Profiles dos agentes | `config.py:300` |

## Como o workspace é resolvido

`resolve_default_workspace` (`config.py:114-154`) tenta, em ordem:

1. argumento explícito (`--project` no CLI, `workspace` na tool MCP);
2. variáveis `ORCHESTRATOR_PROJECT` ou `ORCHESTRATOR_WORKSPACE`;
3. `WORKSPACE_FOLDER_PATHS` (enviado pelo Cursor, aceita vários caminhos);
4. o diretório atual, se tiver `.orchestrator/`;
5. os diretórios-pai do atual;
6. o diretório atual como último recurso.

Sem `.orchestrator/` no destino, `resolve_orchestrator_root` levanta erro
pedindo `orchestrator install` (`config.py:98-104`).

## policies.json

Lido em `load_config` (`config.py:215`) e materializado em `RuntimeLimits`
(`config.py:13-65`). A coluna "onde é lido" indica o consumidor real.

### Ciclo e portões

| Chave | Tipo | Default | Efeito de mudar | Onde é lido |
|---|---|---|---|---|
| `maximum_iterations` | int | 3 | Voltas de executar-testar-validar antes de `INCOMPLETE`. Subir aumenta custo linearmente | `config.py:235`; uso em `tasks/service.py:944` |
| `same_issue_repeat_limit` | int | 2 | Quantas vezes a MESMA issue (id mais descrição normalizada) pode repetir antes de parar | `config.py:236`; `tasks/service.py:1587-1592` e `2411` |
| `max_plan_continuations` | int | 5 | Quantas vezes o runtime manda CONTINUAR um plano incompleto. Continuação não consome iteração | `config.py:237`; `tasks/service.py:1274` |
| `minimum_validation_score` | float | 0.9 | Nota mínima para `COMPLETED` | `config.py:238`; `CompletionGate` em `tasks/service.py:152` |
| `minimum_score_improvement` | float | 0.03 | **Declarada e carregada, nunca consultada.** Nenhum módulo lê `limits.minimum_score_improvement` | só `config.py:239` |
| `maximum_duration_seconds` | int | 8700 | Orçamento total da task; restante abaixo do mínimo de agente vira `INCOMPLETE`. **Tem piso** (0.4.70): valor abaixo da soma dos `agent_timeout_by_role` no percurso `planner→executor→tester→validator→corrector→validator` é elevado a ela, e o pedido fica em `duration_floor_raised_from`. Teto é limite de paciência — subir não faz task nenhuma demorar mais | `config.py` (`_fit_minimum_path`); `execution/timeouts.py:minimum_task_budget_s`; `_remaining_duration_s` em `tasks/service.py` |
| `require_independent_validation` | bool | true | Proíbe validator igual ao executor; força rotação e, sem alternativa, bloqueia com `VAL-IND` | `config.py:247`; `routing/manager.py:65` e `tasks/service.py:1409` |
| `require_deterministic_validation` | bool | true | **Declarada e carregada, nunca consultada.** O validador determinístico roda sempre | só `config.py:250` |
| `require_documentation_review` | bool | true | **Declarada e carregada, nunca consultada.** O gate documental roda sempre; quem barra é `CompletionGate` | só `config.py:253` |

### Timeouts e resiliência de agente

| Chave | Tipo | Default | Efeito de mudar | Onde é lido |
|---|---|---|---|---|
| `agent_timeout_default_s` | int | 1800 | Timeout de papel sem entrada específica | `config.py:243`; `execution/timeouts.py` via `_resolve_agent_timeout` |
| `agent_timeout_by_role` | objeto | planner 900, executor `{run 2400, idle 1200}`, corrector `{run 2400, idle 1200}`, validator 1200, tester 600, skill_selector 120 | **Dois eixos por papel** (0.4.79) — ver abaixo. Merge com os defaults, valor inválido é ignorado. **Mexer no eixo duro move o piso de `maximum_duration_seconds`** (0.4.70). `executor` e `corrector` não recebem o teto cheio quando o restante da task é curto: 600 s ficam reservados para o veredito | `config.py`; `execution/timeouts.py` |
| `agent_infra_fail_fast_count` | int | 3 | Quantos marcadores de falha de infra no stream matam o processo. 0 desliga | `config.py:266`; `agents/process.py:283-289` |
| `agent_no_output_timeout_s` | int | 900 | Eixo ocioso **global**: mata agente após esse tempo sem NENHUMA saída E sem tocar no workspace. Vale para todo papel que não declara `idle_timeout` próprio. 0 desliga | `config.py`; `agents/process.py` |
| `stale_received_ttl_hours` | int | 6 | Idade a partir da qual task `RECEIVED` órfã é auto-cancelada | `config.py:269`; `tasks/service.py:171-202` |
| `orphan_received_adopt_after_s` | int | 120 | Espera antes de outro processo adotar uma `RECEIVED` sem dono. Curto demais rouba a task de quem acabou de criá-la | `config.py`; `_adopt_orphan_received` em `tasks/service.py` |
| `orphan_queued_adopt_after_s` | int | 120 | Lease mínima antes de um poll adotar a cabeça `QUEUED` órfã. `0` desliga. Não ignora dono vivo, teto, escopo nem FIFO | `config.py`; `_adopt_orphan_queued` em `tasks/service.py` |
| `stale_execution_grace_s` | int | 900 | Folga mínima antes de a task **não-terminal** (`PLANNING`/`EXECUTING`) sequer ser julgada: parada há menos que isso é ignorada, mesmo sem dono vivo no lock. Passada a folga, é cancelada quando `updated_at` excede `maximum_duration_seconds` + esta folga **ou** quando nenhum processo vivo segura o lock do workspace — nunca imediatamente por lock órfão. Sem isso, uma task presa barra a fila inteira. `0` desliga | `config.py:289-291`; `_cancel_stale_execution` em `tasks/service.py:237-297` |
| `agent_auto_repair` | bool | true | Ao detectar CLI de agente quebrado, reinstala **uma vez por agente por processo** via `scripts/Update-Agents.ps1 -Only <agente>` e reexecuta o agente. `false` desliga o caminho inteiro: falha `install` volta como está, sem tentativa e **sem** evento `agent_repair` (o evento também não sai quando o agente já foi reparado neste processo). Falta de credencial nunca reinstala — sempre emite evento com o comando de login | `config.py:292`; `tasks/service.py:2640-2670` |
| `agent_repair_timeout_s` | int | 300 | Teto do processo de reinstalação do CLI. Estourado, o reparo é abandonado e a task segue | `config.py:293`; `tasks/service.py:2651-2655`; `agents/repair.py` |

#### Os dois eixos de `agent_timeout_by_role` (0.4.79)

Até a 0.4.78 havia **um** número por papel, teto de relógio puro — e por isso um
agente que morreu mudo no segundo 5 e um agente que produz saída sem parar
morriam os dois no mesmo lugar: no teto. Cada papel aceita agora duas formas:

```json
"agent_timeout_by_role": {
  "planner": 900,
  "executor": { "run_timeout": 2400, "idle_timeout": 1200 }
}
```

| Eixo | O que é | Renovado por sinal? |
|---|---|---|
| `run_timeout` | Teto de relógio da tentativa. Alimenta o `proc.wait` do CLI | **Nunca** |
| `idle_timeout` | Tempo máximo sem progresso observável. Alimenta o watchdog de silêncio (bug-086) | Sim — byte lido no stream ou mudança no workspace |

- **Inteiro puro** (formato antigo) = `run_timeout`, com `idle_timeout` **nulo**.
- `idle_timeout` **nulo** ou `0` = o papel não tem eixo ocioso próprio e cai no
  `agent_no_output_timeout_s` global. É exatamente o comportamento 0.4.78, e é o
  que um `policies.json` não migrado continua fazendo (o merge do template é
  aditivo e não reescreve papel já declarado).
- Só o eixo **duro** entra no piso de `maximum_duration_seconds`: ociosidade não
  gasta orçamento, apenas interrompe mais cedo quem parou de dar sinal.
- Agente morto pelo eixo ocioso sobe como **infra** (`AGENT-NO-OUTPUT-HANG` →
  `_reject_iteration_infra`), nunca como rejeição de mérito, e o erro diz
  *sem sinal de vida (idle_timeout=Ns)*.
- Escolher o número: **folgado**. O erro caro é matar quem estava trabalhando,
  não demorar para enterrar quem morreu. O padrão de 1200 s em
  `executor`/`corrector` é o global de 900 s medido em produção mais 300 s de
  margem, porque são os papéis que passam trechos longos lendo sem imprimir.

Ponto único de decisão: `execution/timeouts.resolve_agent_timeout_policy`.

### Paralelismo

| Chave | Tipo | Default | Efeito de mudar | Onde é lido |
|---|---|---|---|---|
| `allow_parallel_read_only_analysis` | bool | true | **Declarada e carregada, nunca consultada.** Nenhum módulo lê | só `config.py:256` |
| `allow_parallel_workspace_writes` | bool | false | Liga o fan-out: subtarefas em worktrees separados e fusão por patch, só na primeira passada de execução | `config.py:259`; `_fanout_enabled` em `tasks/service.py:2484` |
| `max_parallel_subtasks` | int | 4 | Teto de subtarefas simultâneas do fan-out | `config.py:262`; `tasks/service.py:2484` em diante |
| `max_parallel_tasks` | int | 3 | Teto de **tasks** ativas ao mesmo tempo no projeto (0.4.74). Máximo, não promessa: duas tasks só rodam juntas se os escopos de arquivo forem comprovadamente disjuntos, e escopo desconhecido serializa. **1 restaura o comportamento da 0.4.73** | `config.py`; `_blocking_task_id` em `tasks/service.py` |

O comentário no próprio código registra que as duas primeiras existiam desde o
começo sem nenhum leitor e que a 0.4.61 passou a ler só a segunda
(`config.py:36-41`).

### skill_selection

Extraído por `_skill_selection_limits` (`config.py:157-175`).

| Chave | Tipo | Default | Efeito | Onde é lido |
|---|---|---|---|---|
| `skill_selection.enabled` | bool | true | Desligar pula a fase de seleção de skills | `tasks/service.py:1717` |
| `skill_selection.max_skills` | int | 5 | Quantas skills entram no prompt | `tasks/service.py:1734` |
| `skill_selection.timeout_s` | int | 120 | Teto do agente seletor | `tasks/service.py:1745` |
| `skill_selection.include_user_global` | bool | true | Inclui as skills do home além das do projeto | `skills/discovery.py:65-76` |
| `skill_selection.model_tier` | string | fast | **Declarada e nunca lida.** `_skill_selection_limits` ignora a chave; o seletor sai de `_pick_selector_agent` (`tasks/service.py:1703`) | nenhum |

### context_compaction

Extraído por `_context_compaction_limits` (`config.py:178-197`).

| Chave | Tipo | Default | Efeito | Onde é lido |
|---|---|---|---|---|
| `context_compaction.enabled` | bool | true | Desligar pula learning e compactação no fim da task | `tasks/service.py:3034` |
| `context_compaction.save_learning_before_compact` | bool | true | Invariante: nunca compacta antes de o learning estar em disco | `tasks/service.py:3052` e `3078` |
| `context_compaction.digest_max_chars` | int | 1500 | Tamanho do `session_digest` devolvido ao cliente | `tasks/service.py:3045` |
| `context_compaction.truncate_result_artifacts_chars` | int | 20000 | Corte dos `.txt` em `runtime/results/` | `tasks/service.py:3083` |
| `context_compaction.update_wolf_status` | bool | true | Atualiza `.wolf/STATUS.md` e `.wolf/cerebrum.md` | `tasks/service.py:3065-3068` |

### token_economy

Do bloco inteiro, o runtime lê **uma única chave**:

| Chave | Tipo | Default | Efeito | Onde é lido |
|---|---|---|---|---|
| `token_economy.caveman_enabled` | bool | true | Liga o bloco de ferramentas obrigatórias nos prompts. Desligado, `_required_tooling_block` devolve string vazia | `config.py:263-265`; `tasks/service.py:1688-1689` |

As demais chaves de `token_economy` — `enabled`, `caveman_default`,
`model_routing`, `forbid_max_tier_for`, `require_task_class_before_call_agent`,
`required_agent_tooling` — **não são lidas pelo runtime**. O texto que chega ao
agente é literal no código (`tasks/service.py:1690-1702`), não vem do JSON.

### documentation_policy

`documentation_policy.required_before_completion` e `documentation_policy.message`
**não são lidas pelo runtime**. O gate documental roda incondicionalmente
(`tasks/service.py:1639-1659`) e a exigência efetiva mora em `CompletionGate`.

## models.json

Carregado inteiro em `RuntimeConfig.models` (`config.py:216` e `298`) e
consultado só por `RulesRouter` (`routing/manager.py`).

| Bloco | Tipo | Efeito prático | Onde é lido |
|---|---|---|---|
| `clients.<agente>.model_flag` | string | Flag passada ao CLI antes do nome do modelo | `routing/manager.py:159-160` |
| `clients.<agente>.aliases` | objeto tier para alias | Traduz tier em alias de CLI (`balanced` para `sonnet`) | `routing/manager.py:194` e `266-267` |
| `clients.<agente>.models` | objeto | Alias para nome concreto do modelo | `routing/manager.py:262` e `275` |
| `clients.<agente>.prefer_aliases` | bool (true) | true entrega o alias ao CLI; false resolve para o nome concreto | `routing/manager.py:268-275` |
| `clients.<agente>.task_map` | objeto task_type para alias | Modelo por classe de tarefa quando não há preferência de papel | `routing/manager.py:181-183` |
| `task_classes.<classe>.tier` | string | Tier usado quando `task_map` não cobre a classe | `routing/manager.py:191-193` |
| `role_model_preferences.<papel>.<agente>` | lista | Ordem de tentativa por papel, base do fallback de cota | `routing/manager.py:206` e `235-254` |

Chaves de `models.json` **não lidas por nenhum código**: `version`, `updated`,
`principles`, `token_economy`, `tiers`, `escalation`, `resolution_algorithm`,
`required_agent_tooling`, `always_on_skills`, `clients.*.notes`,
`clients.*.invoke_example`, `clients.*.cli`, `clients.*.selection`, e o campo
`examples` de cada `task_classes`. São documentação embutida e insumo para
scripts PowerShell de rota, não para o runtime.

Detalhe importante do fallback: um modelo só é candidato se estiver
**declarado** no cliente — presente em `models`, em `aliases`, ou entre os
valores de `aliases` (`routing/manager.py:246-253`). Preferência que cita
modelo inexistente é silenciosamente ignorada.

Quando um run esbarra em cota, o par (agente, modelo) entra em
`_exhausted_models` e a próxima tentativa usa o candidato seguinte
(`tasks/service.py:2850-2858` e `2935-2959`).

## manager_model.json

Lido em `config.py:217`, materializado em `ManagerModelConfig`
(`config.py:68-73`).

| Chave | Tipo | Default | Efeito | Onde é lido |
|---|---|---|---|---|
| `provider` | string | `rules` | `openai-compatible` mais `enabled: true` troca o manager determinístico por um provider externo | `config.py:282`; `build_manager`, `manager_model/base.py:148-155` |
| `enabled` | bool | false | Sem isso, o provider externo é ignorado | `config.py:283`; `manager_model/base.py:150` |
| `base_url` | string | `http://localhost:8000/v1` | Endpoint do provider compatível com OpenAI | `config.py:284`; `manager_model/base.py:153` |
| `model` | string | vazio | Nome do modelo no provider | `config.py:285` |
| `api_key_env` | string | `ORCHESTRATOR_MANAGER_API_KEY` | **Nome** da variável de ambiente que guarda a chave. O valor nunca é escrito no arquivo | `config.py:286`; leitura em `manager_model/base.py:152-153` |
| `notes` | string | — | Não lida por ninguém | nenhum |

Mesmo com o provider externo ativo, `LocalLlmManager` delega tudo ao
`RulesManager` nesta versão (`manager_model/base.py:122-145`): o hook existe, a
inferência remota ainda não.

## Arquivos de configuração que ninguém lê

Existem em `.orchestrator/config/` e **nenhum código do runtime, do wrapper Node
ou dos scripts de instalação os consome** (varredura por nome de arquivo em
`runtime/src`, `bin`, `scripts`, `package`, `tests`):

| Arquivo | O que declara | Situação |
|---|---|---|
| `routing.json` | `default_strategy`, `routes` por classe de tarefa, `prefer_clients`, `tier` | Nenhum leitor. O roteamento real está em `routing/manager.py`, com preferências hardcoded (`agents/__init__.py:130-135`) e em `models.json` |
| `validation.json` | `validators`, `scoring.pass_threshold`, `deterministic_checks` | Nenhum leitor no runtime. O limiar efetivo vem de `policies.json` → `minimum_validation_score` |
| `tools.json` | `enabled`, `registry_path`, `allow_optional`, `sandbox_untrusted` | Nenhum leitor |
| `orchestrator.json` | `version`, `name`, `runtime_dir`, `memory_dir`, `skills_dir`, `agents_dir` | Nenhum leitor; os diretórios são hardcoded no runtime |

Manter esses arquivos não quebra nada, mas editá-los não muda comportamento
nenhum. Está registrado em `limitacoes.md`.

## Variáveis de ambiente

Sempre por nome lógico. Nenhum valor aparece nesta documentação.

| Variável | Finalidade | Obrigatória | Ambiente | Onde é lida |
|---|---|---|---|---|
| `ORCHESTRATOR_CHILD_AGENT` | Marca o processo como agente filho; bloqueia delegação aninhada | Não — o runtime seta `1` no filho | Processo do agente delegado | `agents/process.py:57-65` e `157` |
| `ORCHESTRATOR_PROJECT` | Workspace padrão | Não | Cliente MCP ou CLI | `config.py:128` |
| `ORCHESTRATOR_WORKSPACE` | Alternativa à anterior | Não | Idem | `config.py:128` |
| `WORKSPACE_FOLDER_PATHS` | Workspace informado pelo Cursor | Não | Cursor | `config.py:135` |
| `ORCHESTRATOR_CALLER` | Override explícito da superfície chamadora | Não | Automação e testes | `callers.py:26` e `72` |
| `ORCHESTRATOR_CALLER_MCP` | Marcada pelo servidor MCP antes de atender qualquer tool | Não — automática | Processo do servidor MCP | `callers.py:23`; `mcp/server.py:14` |
| `ORCHESTRATOR_MCP_WAIT_TIMEOUT` | Teto do modo `wait` das tools MCP (segundos) | Não; default 120 | Cliente MCP | `mcp/server.py:35` |
| `ORCHESTRATOR_MCP_ALLOW_REMOTE` | Autoriza bind fora de localhost | Não; sem ela, bind remoto é recusado | Host do servidor MCP | `mcp/server.py:268-275` |
| `ORCHESTRATOR_MANAGER_API_KEY` | Nome padrão da variável que guarda a credencial do manager LLM opcional. O valor fica só no ambiente | Só com provider externo ativo | Host do runtime | `manager_model/base.py:152` |
| `ORCHESTRATOR_PROJECTS_REGISTRY` | Caminho alternativo do registro da frota | Não | Host do instalador | `scripts/Orchestrator.Common.ps1:1089-1091` |
| `CLAUDECODE`, `CLAUDE_PROJECT_DIR` | Sinais de que o chamador é Claude Code | Setadas pelo próprio CLI | Sessão Claude Code | `callers.py:80-83` |
| `CURSOR_*`, `TERM_PROGRAM` | Sinais de que o chamador é o Cursor | Setadas pelo Cursor | Sessão Cursor | `callers.py:85-88` |
| `CODEX_HOME` | Sinal de que o chamador é o Codex | Setada pelo Codex | Sessão Codex | `callers.py:90-91` |
| `PYTHONPATH`, `PYTHONUTF8`, `PYTHONIOENCODING` | Injetadas pelo wrapper Node para achar o pacote e fixar UTF-8 | Automáticas | Subprocesso Python | `bin/orchestrator.js:330-335` |

O executor de processos **reescreve linhas com cara de segredo** antes de
gravar log: qualquer linha com `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD` ou
`AUTHORIZATION` e um separador vira `[REDACTED]` (`agents/process.py:46` e
`68-77`). O ambiente completo é repassado ao filho, mas não é logado
(`sanitize_env`, `agents/process.py:49-54`).

## Precedência efetiva

1. Parâmetro da chamada (`--max-iterations`, `--timeout`, `--executor`,
   `--validator`, `--planner`) — vira `TaskConstraints` na criação da task
   (`tasks/service.py:261-271`), e é o que o laço consulta.
2. `policies.json` do projeto — vira o default dessas restrições.
3. Default do código (`RuntimeLimits`, `config.py:13-65`) — quando a chave não
   existe no JSON.

Profile de agente entra só depois: `ProfileCliAdapter` usa
`timeout_default_s` do profile **apenas** se o request não trouxer timeout útil
(`agents/base_adapters.py:151-156`).
