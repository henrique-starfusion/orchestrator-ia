> **LEGADO — não use para primeira instalação**
>
> Este prompt descreve o fluxo antigo baseado em `.claude/` como fonte canônica.
> **A fonte canônica atual é `.orchestrator/`.**
>
> Para instalação determinística (uma linha, na pasta do projeto):
>
> ```bash
> npx --yes github:henrique-starfusion/bootstrap-agents#develop init
> ```
>
> ```powershell
> gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/bootstrap-agents/contents/get.ps1?ref=develop" | iex
> ```
>
> Consulte `README.md`, `docs/quickstart-oneliner.md` e `docs/cli-reference.md`.
> Este arquivo está em `docs/legacy/` e **não é usado** pelo instalador atual.

# Inicialização de ambiente multiagente usando `.claude`

Você é o Codex CLI responsável por **estruturar pela primeira vez** (ou completar o que falta) o ambiente de agentes de IA deste projeto.

Este prompt é para modo `install` do `bootstrap-agents.bat`.

**Não use este prompt para remount:** se `.claude/VERSION` já existir e o workspace estiver estruturado, o bootstrap deve apenas verificar ou fazer upgrade incremental. Não apague `.claude/`, não faça backup destrutivo e não reconstrua do zero.

Execute as etapas diretamente na raiz do projeto.

Não pare no planejamento.

Não use as pastas:

```text
.ai/
.ai-*/
orchestrator/
```

Toda a infraestrutura compartilhada de agentes, skills, memória, ferramentas, execução e orquestração deverá ficar dentro de:

```text
.claude/
```

Grave `.claude/VERSION` com a mesma versão do pacote bootstrap (`VERSION` na raiz do pacote).

A pasta `docs/` continuará sendo usada exclusivamente para documentação técnica e funcional do projeto.

---

# 1. Objetivo

Criar uma infraestrutura multiagente **genérica**, limpa e compartilhada, utilizável em qualquer tipo de repositório, por:

* Claude Code;
* Codex CLI;
* Gemini CLI;
* Kimi CLI;
* OpenCode;
* Cursor;
* Qwen Code;
* GitHub Copilot CLI;
* outros agentes CLI encontrados na máquina.

A pasta `.claude/` será a fonte canônica do projeto para:

* configuração;
* regras;
* agentes;
* skills;
* prompts;
* memória;
* orquestração;
* ferramentas;
* MCPs;
* scripts;
* runtime;
* logs;
* relatórios.

Os demais agentes não deverão possuir configurações independentes e divergentes.

Quando um agente exigir um arquivo próprio, crie somente um pequeno adaptador que redirecione para `.claude/`.

---

# 2. Estado esperado antes da execução

O `bootstrap-agents.bat` opera por versão e de forma incremental:

| Modo | Quando | O que fazer |
|---|---|---|
| `install` | sem `.claude/` ou sem `.claude/VERSION` | este prompt pode estruturar o ambiente |
| `verify` | versões iguais | só validar; **não** reconstruir |
| `upgrade` | pacote mais novo | só adicionar o que a nova versão exige |
| `refuse` | workspace mais novo que o pacote | abortar |

Antes de qualquer escrita destrutiva, leia `.claude/VERSION` (se existir).

Se a estrutura canônica já estiver presente:

1. **não** remova o conteúdo de `.claude/`;
2. **não** remova adaptadores válidos (`CLAUDE.md`, `AGENTS.md`, etc.) só para recriá-los;
3. complete apenas arquivos/pastas ausentes;
4. atualize `.claude/VERSION` somente após migrações aditivas bem-sucedidas.

Limpeza de caminhos legados (`.codex/`, `.agents/`, etc.) só com confirmação explícita do bootstrap (`--legacy-cleanup`), nunca como padrão.

Valide o estado antes de prosseguir. Não confie cegamente no bootstrap.

---

# 3. Autonomia

Você está autorizado a executar sem solicitar confirmação intermediária:

* criar arquivos e pastas dentro do projeto;
* modificar arquivos dentro do projeto;
* remover configurações antigas de IA ainda restantes;
* instalar dependências locais do projeto;
* instalar ferramentas de apoio em ambiente de usuário quando estritamente necessário;
* atualizar ferramentas já instaladas;
* executar PowerShell, CMD, Git, Node.js, Python e Docker;
* chamar outros agentes CLI;
* criar skills;
* configurar MCPs;
* executar testes;
* corrigir erros;
* criar documentação;
* configurar hooks depois de validá-los.

Não execute:

* exclusão fora da raiz do projeto;
* formatação ou alteração de discos;
* exclusão de repositório remoto;
* `git push --force`;
* deploy em produção;
* leitura ou cópia de credenciais;
* alteração destrutiva global do Windows;
* modificação de contas;
* desativação de antivírus ou firewall;
* instalação de pacote sem verificar origem.

---

# 4. Regra crítica sobre hooks

Durante toda a inicialização:

```text
NÃO ATIVE HOOKS
```

Nenhum hook de:

* `SessionStart`;
* `PreToolUse`;
* `PostToolUse`;
* `Stop`;
* shell guard;
* validação automática;
* OpenWolf;
* Graphify;
* MCP;
* segurança;

deverá ser ativado antes da conclusão dos testes.

Primeiro crie os scripts.

Depois teste cada script diretamente.

Somente após todos passarem, configure os hooks.

Um hook com falha não poderá bloquear o agente.

Todo hook deverá:

* receber entrada válida;
* validar parâmetros opcionais;
* nunca chamar `Join-Path` com argumento vazio;
* nunca solicitar parâmetros interativamente;
* usar código de saída zero quando não houver ação necessária;
* possuir timeout;
* registrar erros sem bloquear a sessão;
* funcionar no Windows PowerShell 5.1 e, quando possível, PowerShell 7;
* ser testado isoladamente antes da ativação.

---

# 5. Limpeza complementar

Somente no modo `install`, ou quando `--legacy-cleanup` tiver sido solicitado de forma explícita.

Em `verify` / `upgrade`, **não** mova nem apague configurações existentes: apenas reporte divergências.

Quando a limpeza for autorizada, inspecione a raiz e remova referências antigas de IA que conflitem com `.claude/`.

Remova, quando existirem e a limpeza estiver autorizada:

```text
.codex/
.cursor/
.agents/
.agent/
.gemini/
.kimi/
.opencode/
.openai/
.aider/
.continue/
.cline/
.roo/
.roocode/
.windsurf/
.wolf/
.graphify/
.codegraph/
.mcp/
.ai/
.ai-bootstrap/
.ai-backups/
orchestrator/
graphify-out/
```

Remova também:

```text
CLAUDE.md
AGENTS.md
CODEX.md
GEMINI.md
KIMI.md
CURSOR.md
OPENAI.md
AI.md
.cursorrules
mcp.json
.mcp.json
```

Dentro de `.github/`, remova somente:

```text
.github/agents/
.github/skills/
.github/copilot-instructions.md
```

quando forem configurações antigas de IA.

Não remova:

* `.git/`;
* código-fonte;
* testes;
* documentação funcional;
* migrations;
* arquivos de banco;
* assets;
* pipelines legítimos;
* configurações de build;
* configurações de aplicação;
* `.vscode/` que não sejam específicas de IA.

Antes de remover qualquer item sobrevivente, copie-o para:

```text
.claude/backups/<timestamp>/
```

---

# 6. Estrutura canônica

Crie esta estrutura:

```text
.claude/
├── README.md
├── VERSION
├── settings.json
│
├── bootstrap/
│   ├── status.json
│   ├── environment.json
│   ├── cleanup-report.json
│   ├── installation-report.json
│   └── validation-report.json
│
├── agents/
│   ├── registry.json
│   ├── capabilities.json
│   ├── profiles/
│   ├── adapters/
│   ├── prompts/
│   └── results/
│
├── rules/
│   ├── project.md
│   ├── development.md
│   ├── security.md
│   ├── testing.md
│   ├── design.md
│   ├── documentation.md
│   ├── memory.md
│   ├── orchestration.md
│   └── worker-mode.md
│
├── skills/
│   ├── orchestrate/
│   ├── analyze-project/
│   ├── analyze-task/
│   ├── plan-task/
│   ├── select-agents/
│   ├── call-agent/
│   ├── run-tests/
│   ├── validate-result/
│   ├── correction-loop/
│   ├── save-knowledge/
│   ├── update-documentation/
│   ├── architecture-review/
│   ├── code-review/
│   ├── security-review/
│   ├── design-review/
│   ├── accessibility-review/
│   ├── performance-review/
│   ├── database-review/
│   ├── api-review/
│   ├── container-review/
│   ├── dependency-review/
│   ├── external/
│   ├── quarantined/
│   ├── rejected/
│   └── registry.json
│
├── memory/
│   ├── README.md
│   ├── project/
│   ├── architecture/
│   ├── decisions/
│   ├── episodes/
│   ├── tasks/
│   ├── performance/
│   ├── strategies/
│   ├── failures/
│   ├── lessons/
│   ├── entities/
│   ├── summaries/
│   ├── graph/
│   ├── archive/
│   └── index.json
│
├── orchestration/
│   ├── policies.json
│   ├── routing.json
│   ├── validation.json
│   ├── roles.json
│   ├── workflows/
│   ├── templates/
│   └── schemas/
│
├── mcp/
│   ├── registry.json
│   ├── configs/
│   ├── audits/
│   └── disabled/
│
├── tools/
│   ├── registry.json
│   ├── openwolf/
│   ├── graphify/
│   └── optional/
│
├── scripts/
│   ├── detect/
│   ├── agents/
│   ├── memory/
│   ├── validation/
│   ├── installation/
│   ├── hooks/
│   └── maintenance/
│
├── hooks/
│   ├── disabled/
│   ├── tested/
│   └── active/
│
├── runtime/
│   ├── tasks/
│   ├── plans/
│   ├── prompts/
│   ├── results/
│   ├── validations/
│   ├── logs/
│   ├── locks/
│   ├── temporary/
│   └── reports/
│
└── backups/
```

Use arquivos `.gitkeep` somente quando necessário.

Não crie centenas de arquivos vazios sem função.

---

# 7. Criar o arquivo `CLAUDE.md`

Crie um novo `CLAUDE.md` na raiz.

Ele deverá ser pequeno e carregar a fonte canônica:

```text
.claude/rules/project.md
.claude/rules/development.md
.claude/rules/security.md
.claude/rules/testing.md
.claude/rules/design.md
.claude/rules/documentation.md
.claude/rules/memory.md
.claude/rules/orchestration.md
```

Inclua:

```text
A pasta .claude é a fonte canônica compartilhada para todos os agentes.

Nenhuma configuração antiga deve prevalecer sobre .claude.

Quando ORCHESTRATOR_CHILD_AGENT=1 estiver definido, o agente está em modo
trabalhador e não poderá criar equipes, delegar tarefas ou iniciar uma nova
orquestração.
```

---

# 8. Criar adaptadores mínimos

Depois de detectar quais agentes estão disponíveis, crie apenas os arquivos mínimos necessários.

## Codex

Quando Codex estiver disponível, crie:

```text
AGENTS.md
```

O arquivo deve apontar para `.claude/rules/` e `.claude/memory/`.

Não recrie `.codex/`, salvo se a versão instalada exigir algum arquivo estritamente necessário.

## Gemini

Quando Gemini estiver disponível, crie:

```text
GEMINI.md
```

## Kimi

Quando Kimi estiver disponível, crie:

```text
KIMI.md
```

## Cursor

Quando Cursor estiver disponível, crie somente as rules mínimas no formato atual suportado.

Não duplique memória, skills ou orquestração.

---

# 9. Detectar os agentes CLI

Detecte:

```text
claude
codex
gemini
kimi
opencode
qwen
qwen-code
copilot
github-copilot
aider
goose
amp
kiro
cursor
continue
openhands
openclaw
droid
factory
```

No Windows, use:

```powershell
Get-Command <nome> -ErrorAction SilentlyContinue
where.exe <nome>
```

Obtenha:

* caminho;
* versão;
* ajuda;
* modo não interativo;
* suporte a JSON;
* suporte a sandbox;
* suporte a leitura;
* suporte a escrita;
* suporte a sessão;
* suporte a MCP;
* arquivos de instruções;
* códigos de saída.

Não use comandos inventados.

Consulte primeiro:

```text
<cli> --help
<cli> --version
```

Teste cada CLI com:

```text
Responda exatamente com:
ORCHESTRATOR_AGENT_OK
```

Use timeout.

Use modo somente leitura quando disponível.

Salve em:

```text
.claude/bootstrap/agents-detected.json
.claude/agents/registry.json
```

Classifique:

```text
available
installed_but_not_authenticated
installed_but_failed
installed_but_not_headless
incompatible
not_installed
unknown
```

---

# 10. Chamada dos agentes

Crie:

```text
.claude/scripts/agents/call-agent.ps1
.claude/scripts/agents/call-agent.bat
```

Parâmetros:

```text
-agent
-role
-workspace
-promptFile
-outputFile
-timeout
-readOnly
-sessionId
```

O executor deverá:

1. ler `.claude/agents/registry.json`;
2. validar o agente;
3. montar o comando sem `Invoke-Expression`;
4. usar uma lista segura de argumentos;
5. definir:

```text
ORCHESTRATOR_CHILD_AGENT=1
ORCHESTRATOR_TASK_ID=<id>
ORCHESTRATOR_ROLE=<papel>
```

6. aplicar timeout;
7. capturar stdout;
8. capturar stderr;
9. capturar exit code;
10. salvar logs;
11. normalizar saída;
12. impedir escrita paralela;
13. impedir recursão;
14. ocultar segredos.

O prompt de todo agente filho deverá começar com:

```text
Você é um agente trabalhador chamado pelo agente orquestrador.

Você não é o orquestrador.
Não monte uma equipe.
Não delegue esta atividade.
Não chame outros agentes.
Não reinicie a orquestração.
Execute exclusivamente o papel informado.
```

---

# 11. Agente orquestrador

Crie a skill:

```text
.claude/skills/orchestrate/SKILL.md
```

Fluxo:

```text
receber
→ analisar
→ recuperar memória
→ definir critérios
→ selecionar planejador
→ planejar
→ selecionar executor
→ executar
→ selecionar testador
→ testar
→ selecionar validador
→ validar
→ corrigir
→ testar novamente
→ validar novamente
→ concluir ou atingir limite
→ salvar conhecimento
```

Papéis obrigatórios:

* orquestrador;
* planejador;
* executor;
* testador;
* validador.

Regras:

1. Toda tarefa deve ser validada.
2. O executor não poderá ser o único validador.
3. Use agentes diferentes quando disponíveis.
4. Quando existir apenas um agente, use sessões separadas.
5. Testes determinísticos são obrigatórios quando aplicáveis.
6. Escrita paralela no mesmo workspace é proibida.
7. Correções voltam ao executor original.
8. O loop deve possuir limite.
9. Nenhuma tarefa será concluída somente porque o agente afirmou que terminou.
10. Toda conclusão deve possuir evidências.

Configuração inicial:

```json
{
  "maximum_iterations": 3,
  "same_issue_repeat_limit": 2,
  "minimum_validation_score": 0.9,
  "minimum_score_improvement": 0.03,
  "require_independent_validation": true,
  "require_deterministic_validation": true,
  "allow_parallel_read_only_analysis": true,
  "allow_parallel_workspace_writes": false
}
```

---

# 12. Memória compartilhada

Toda a memória deverá ficar em:

```text
.claude/memory/
```

Não use memória global como fonte de verdade.

Não use `.wolf/` como fonte canônica.

OpenWolf poderá usar seus próprios arquivos internamente, mas deverá sincronizar conhecimento validado para `.claude/memory/`.

Tipos:

```text
project
architecture
decisions
episodes
tasks
performance
strategies
failures
lessons
entities
summaries
graph
archive
```

Formato mínimo:

```json
{
  "id": "",
  "type": "",
  "status": "candidate|validated|active|stale|archived",
  "statement": "",
  "summary": "",
  "confidence": 0,
  "evidence": [],
  "source_task": "",
  "related_files": [],
  "related_commit": null,
  "created_at": "",
  "last_verified_at": "",
  "created_by_agent": "",
  "validated_by_agent": ""
}
```

Somente informação com evidência poderá ser marcada como `active`.

---

# 13. OpenWolf

Verifique se OpenWolf está instalado:

```text
openwolf --version
openwolf --help
```

Quando existir:

1. descubra como foi instalado;
2. verifique a versão mais recente em fonte oficial;
3. atualize pelo mesmo gerenciador;
4. remova a configuração antiga do projeto;
5. inicialize novamente;
6. configure para usar `.claude/memory/` como memória canônica;
7. não ative hooks imediatamente;
8. execute `openwolf scan` somente depois da configuração;
9. teste leitura e escrita;
10. ative os hooks somente se os testes passarem.

Quando não existir:

1. pesquise o projeto oficial;
2. audite o instalador;
3. instale somente se for verificável e compatível;
4. não bloqueie o restante se a instalação falhar.

Registre:

```text
.claude/tools/openwolf/audit.md
.claude/tools/openwolf/status.json
```

---

# 14. Graphify

Verifique:

```text
graphify --version
graphify --help
```

Quando existir:

1. identificar o pacote correto;
2. verificar o ambiente Python usado;
3. verificar dependências;
4. verificar se o modelo configurado ainda existe;
5. atualizar o pacote;
6. remover configuração antiga;
7. inicializar novamente;
8. gerar o grafo;
9. testar consulta;
10. salvar resultados em:

```text
.claude/memory/graph/
```

Não configure simultaneamente Graphify e CodeGraph como fontes concorrentes.

Nesta versão, Graphify será a ferramenta de grafo preferencial.

Remova bloqueios antigos que obriguem o uso de CodeGraph.

Não recrie `.codegraph/`.

Se Graphify continuar incompatível:

* registre o erro;
* não force;
* mantenha a pasta `.claude/memory/graph/`;
* prossiga sem grafo.

Registre:

```text
.claude/tools/graphify/audit.md
.claude/tools/graphify/status.json
```

---

# 15. Skills externas

Avalie:

* Ponytail;
* Superpowers;
* Agent Skills;
* SkillsLLM;
* skills de design;
* skills de arquitetura;
* skills de testes;
* skills de segurança;
* skills de documentação;
* skills de frontend;
* skills de backend;
* skills de banco;
* skills de DevOps.

Toda skill externa deverá entrar primeiro em:

```text
.claude/skills/quarantined/
```

Audite:

* fonte;
* mantenedor;
* commit;
* licença;
* scripts;
* comandos;
* permissões;
* acesso à rede;
* referências externas;
* conflito com a orquestração.

Somente depois mova para:

```text
.claude/skills/external/
```

Não instale coleções inteiras sem necessidade.

Não permita que uma skill externa instale hooks automaticamente.

---

# 16. MCPs

Configure inicialmente apenas:

## Context7

Use documentação oficial e configuração atual da versão detectada.

## Playwright

Somente quando o projeto tiver aplicação web.

## GitHub

Somente quando houver necessidade e autenticação disponível.

## Figma

Somente quando houver fluxo real de design.

## Banco de dados

Somente quando o banco for detectado e nunca conectando automaticamente à produção.

Salve tudo em:

```text
.claude/mcp/
```

Crie adaptadores específicos por agente somente quando necessário.

Não salve tokens no projeto.

---

# 17. Análise inicial do projeto

Analise o projeto real e documente:

* objetivo;
* domínio;
* usuários;
* linguagens;
* frameworks;
* módulos;
* entrypoints;
* arquitetura;
* camadas;
* dependências;
* fluxo de dados;
* APIs;
* banco;
* cache;
* filas;
* integrações;
* autenticação;
* autorização;
* frontend;
* backend;
* design system;
* testes;
* containers;
* CI/CD;
* segurança;
* observabilidade;
* dívida técnica;
* riscos;
* lacunas.

Classifique informações como:

```text
observado
inferido
desconhecido
recomendado
```

---

# 18. Documentação

Use exclusivamente:

```text
docs/
```

Crie ou atualize:

```text
docs/README.md
docs/project-overview.md
docs/architecture.md
docs/codebase-structure.md
docs/development-guide.md
docs/testing-guide.md
docs/deployment-guide.md
docs/security.md
docs/design-system.md
docs/data-model.md
docs/integrations.md
docs/api.md
docs/troubleshooting.md
docs/agent-environment.md
```

Crie:

```text
docs/decisions/
docs/diagrams/
docs/modules/
docs/workflows/
docs/generated/
```

Inclua diagramas Mermaid para:

* contexto;
* componentes;
* módulos;
* fluxo principal;
* orquestração;
* memória;
* agentes;
* MCPs.

Não sobrescreva documentação existente sem primeiro incorporá-la.

---

# 19. Hooks novos

Depois que todo o ambiente estiver funcionando, crie hooks novos em:

```text
.claude/hooks/tested/
```

Antes de ativar:

1. execute cada hook sem argumentos;
2. execute com entrada mínima;
3. execute com entrada inválida;
4. execute quando arquivos esperados estiverem ausentes;
5. confirme que nunca abre prompt interativo;
6. confirme que não solicita `ChildPath`;
7. confirme que retorna em menos de cinco segundos;
8. confirme que erro interno não bloqueia o agente;
9. confirme compatibilidade com PowerShell 5.1;
10. registre resultado.

Somente hooks aprovados serão copiados para:

```text
.claude/hooks/active/
```

Somente então atualize `.claude/settings.json`.

Comece com hooks mínimos.

Não ative hooks de OpenWolf, Graphify, memória, shell guard e sincronização todos ao mesmo tempo.

Ative um por vez e valide novamente.

---

# 20. Validação

Valide:

* JSON;
* YAML;
* Markdown;
* PowerShell;
* Batch;
* shell scripts;
* caminhos;
* registro de agentes;
* chamada de agentes;
* timeout;
* prevenção de recursão;
* memória;
* skills;
* MCPs;
* OpenWolf;
* Graphify;
* hooks;
* documentação.

Execute uma tarefa multiagente somente de leitura:

```text
Analise o projeto e identifique os cinco módulos mais importantes.
Não altere código.
```

Depois execute teste de escrita apenas em:

```text
.claude/runtime/temporary/test-workspace/
```

Não altere o código real no teste inicial.

---

# 21. Relatório final

Crie:

```text
.claude/runtime/reports/initialization-report.md
```

Inclua:

* ambiente;
* itens removidos;
* backup;
* agentes detectados;
* agentes funcionais;
* adaptadores;
* skills;
* MCPs;
* OpenWolf;
* Graphify;
* memória;
* orquestração;
* documentação;
* hooks;
* testes;
* falhas;
* correções;
* limitações;
* ações manuais.

Não declare sucesso sem evidência.

---

# 22. Condição de conclusão

Somente finalize quando:

* a limpeza complementar estiver concluída;
* `.claude/` estiver reconstruída;
* os agentes estiverem detectados;
* Codex estiver configurado como executor;
* adaptadores mínimos existirem;
* a memória estiver compartilhada;
* a orquestração estiver criada;
* skills tiverem sido auditadas;
* MCP Context7 tiver sido avaliado;
* OpenWolf tiver sido atualizado ou documentado como indisponível;
* Graphify tiver sido atualizado ou documentado como indisponível;
* o projeto tiver sido analisado;
* `docs/` tiver sido atualizada;
* os hooks novos tiverem sido testados;
* um teste multiagente tiver sido realizado;
* o relatório final tiver sido criado.

Execute agora todas as etapas sem solicitar confirmações intermediárias.
