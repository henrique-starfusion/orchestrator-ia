# Documentação do @starfusion/orchestrator

Índice mestre da documentação deste repositório (`bootstrap-agents`, pacote npm
`@starfusion/orchestrator`, versão `0.4.84` em `VERSION:1` e `package.json:3`).

Esta pasta tem dois tipos de documento:

- **Documentos-base desta rodada** (listados abaixo): escritos a partir
  da leitura do código, cada afirmação não-óbvia com evidência `arquivo:linha`
  ou nome de símbolo.
- **Documentos anteriores** (`orquestrador.md`, `cli-reference.md`,
  `troubleshooting.md`, `installer-architecture.md`, e as pastas `archive/`,
  `audits/`, `legacy/`, `maintenance/`, `cleanup/`): material histórico e
  operacional, útil, mas **não** reconferido linha a linha nesta rodada.
  Divergências encontradas entre eles e o código estão registradas em
  `limitacoes.md`.

## Documentos-base

| Documento | O que responde |
|---|---|
| `visao-geral.md` | O que o produto é, que problema resolve, quem são os atores, vocabulário do domínio |
| `arquitetura.md` | Componentes reais (instalador Node+PowerShell, runtime Python, adapters, MCP, SQLite) e como se ligam; diagrama Mermaid |
| `fluxo-de-execucao.md` | Ciclo de vida de uma task estado a estado, com os pontos de decisão reais |
| `configuracao.md` | Cada chave de `.orchestrator/config/` — finalidade, tipo, default, efeito, onde é lida; chave declarada e não lida marcada como tal |
| `operacao.md` | Instalar, atualizar, propagar para a frota, acompanhar, cancelar, retomar, e o que observar quando parece travado |
| `integracao-agentes.md` | Como cada CLI é acionado, o que o install/update configura por projeto, e o mecanismo anti-recursão de agente filho |
| `dados.md` | Schema real do SQLite, tabela a tabela, com quem escreve em cada uma |
| `testes.md` | Organização da suíte (pytest do runtime + suíte PowerShell), o que cada grupo cobre, como rodar |
| `limitacoes.md` | Limites conhecidos, pendências e hipóteses levantadas durante esta documentação |
| `regras-de-negocio.md` | Invariantes que governam uma execução, com a razão operacional e a evidência de cada regra |
| `catalogo-de-funcionalidades.md` | Funcionalidades implementadas por camada, ponto de entrada, exposição e evidência no código |

## Por onde começar, segundo o perfil

### Quem vai usar (pede tarefas ao orquestrador, de um chat ou do terminal)

1. `visao-geral.md` — entender o que é uma *task*, uma *iteração* e um *loop*.
2. `catalogo-de-funcionalidades.md` — localizar a superfície disponível e seu
   ponto de entrada.
3. `operacao.md` — seções "Acompanhar uma task", "Cancelar", "Retomar" e
   "Parece travado".
4. `integracao-agentes.md` — a seção "Anti-recursão: agente filho", que explica
   por que um agente delegado não pode delegar de novo.

### Quem vai operar (instala, atualiza e mantém a frota de projetos)

1. `operacao.md` — instalar, atualizar, propagar, diagnosticar.
2. `configuracao.md` — o que cada chave muda de verdade.
3. `dados.md` — onde ficam os registros para auditar uma execução
   (`.orchestrator/data/orchestrator.db`, definido em
   `runtime/src/orchestrator_runtime/config.py:295`).
4. `limitacoes.md` — o que **não** funciona como a documentação antiga diz.

### Quem vai contribuir (mexe no código do runtime ou do instalador)

1. `arquitetura.md` — mapa dos módulos e das fronteiras.
2. `regras-de-negocio.md` — invariantes que não podem ser removidas numa
   refatoração sem reabrir os incidentes que as motivaram.
3. `fluxo-de-execucao.md` — o loop principal é `TaskService._execute_loop`
   (`runtime/src/orchestrator_runtime/tasks/service.py:767`); ler antes de tocar
   em qualquer estado.
4. `dados.md` — todo acesso ao banco passa por
   `runtime/src/orchestrator_runtime/tasks/repository.py`; nenhum outro módulo
   instancia as classes `*Row`.
5. `testes.md` — como rodar as duas suítes antes de abrir mudança.
6. `limitacoes.md` — dívidas já identificadas, para não redescobri-las.

## Convenção de evidência

Toda afirmação não-óbvia nestes dez documentos aponta para um arquivo do
repositório, no formato `caminho/arquivo.py:linha` ou pelo nome do símbolo
(`TaskService._execute_loop`, `RulesRouter.select_plan`). Números de linha
referem-se ao estado do repositório no momento desta rodada; símbolos
sobrevivem melhor a refatorações — quando a linha não bater, procure o símbolo.

Nada nestes documentos contém valor de segredo. Variáveis de ambiente aparecem
só por nome lógico, finalidade e obrigatoriedade (ver `configuracao.md`).
