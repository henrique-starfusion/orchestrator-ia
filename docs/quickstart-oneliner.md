# Quickstart — uma linha de comando

Modelo mental igual ao [OpenWolf](https://github.com/cytostack/openwolf) e ao Graphify:

1. obter o CLI/pacote;
2. na pasta do projeto, rodar `init`.

## Opção A — npm / npx (recomendado)

Na raiz do projeto-alvo:

```bash
npx --yes github:henrique-starfusion/bootstrap-agents#develop init
```

Instalação global (reutilizar em vários projetos):

```bash
npm install -g github:henrique-starfusion/bootstrap-agents#develop
orchestrator init
```

Alias:

```bash
mao init
```

Comandos úteis depois:

```bash
orchestrator status
orchestrator verify
orchestrator update
```

Atualizar o **CLI global** (pacote npm) e depois a estrutura do projeto:

```bash
npm install -g github:henrique-starfusion/bootstrap-agents#develop
cd C:\caminho\do\seu\projeto
orchestrator update
```

Ou só com npx (sem global):

```bash
npx --yes github:henrique-starfusion/bootstrap-agents#develop update
```

`update` sincroniza a estrutura `.orchestrator/` do projeto com o pacote (aditivo; use `--force` para reaplicar managed).

> Repositório privado: o npm/npx usa suas credenciais Git (`gh auth` / credential helper).

## Opção B — PowerShell + GitHub CLI

Na raiz do projeto-alvo:

```powershell
gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/bootstrap-agents/contents/get.ps1?ref=develop" | iex
```

O script:

1. clona/atualiza o cache em `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator`;
2. executa `install` no diretório atual.

Outros comandos:

```powershell
# depois de ter o cache, ou com clone local:
.\get.ps1 status
.\get.ps1 upgrade -Force
```

## Opção C — clone local

```powershell
git clone -b develop https://github.com/henrique-starfusion/bootstrap-agents.git
cd seu-projeto
..\bootstrap-agents\get.ps1
```

## Resultado esperado

```text
seu-projeto/
├── .orchestrator/          ← fonte canônica
├── CLAUDE.md               ← adaptador (se Claude detectado)
├── AGENTS.md               ← adaptador (se Codex/OpenCode detectado)
└── ...
```

## Comparativo

| Ferramenta | Install global | Init no projeto |
|---|---|---|
| OpenWolf | `npm i -g openwolf` | `openwolf init` |
| Graphify | `uv tool install ...` / npm | `graphify install` |
| Este pacote | `npm i -g github:.../bootstrap-agents#develop` | `orchestrator init` |

## Segurança

- A instalação estrutural é **determinística** (templates + PowerShell).
- Não use agentes de IA para criar a árvore.
- O one-liner PowerShell usa `gh api` autenticado (sem gravar tokens no projeto).
- Prefira `npx`/`npm` ou `get.ps1` versionado em vez de scripts anônimos de terceiros.
