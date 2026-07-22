# Security Policy — Orquestrador IA Multiagente

## Versões suportadas

| Versão | Suporte de segurança |
|--------|----------------------|
| 0.4.x  | Sim (atual) |
| < 0.4  | Melhor esforço; prefira atualizar |

## Como reportar uma vulnerabilidade

**Não** abra issue pública com detalhes exploráveis.

1. Prefira **GitHub Security Advisories** neste repositório:  
   [Report a vulnerability](https://github.com/henrique-starfusion/orchestrator-ia/security/advisories/new)
2. Ou contate o mantenedor pelo perfil GitHub [@henrique-starfusion](https://github.com/henrique-starfusion).

Inclua, se possível:

- versão do pacote (`orchestrator version` / tag);
- ambiente (OS, Cursor/MCP ou CLI);
- passos para reproduzir;
- impacto esperado (leitura de workspace, fuga de path, exposição de secrets, etc.).

Resposta inicial esperada: alguns dias úteis. Correções entram no `CHANGELOG.md` e em releases.

## Escopo

**No escopo**

- Runtime MCP (`orchestrator mcp serve`)
- Allowlist de workspace e superfícies de tools
- Vazamento de secrets em logs/echo
- Bypass de `read_only` / `fake_agents` / validação independente
- Instalador escrevendo fora do projeto sem intenção

**Fora do escopo (em geral)**

- Segurança dos CLIs de terceiros (Claude, Codex, etc.)
- Modelos/LLMs e prompt injection “social” sem bug no orquestrador
- Projetos-alvo do usuário (código instalado pelo orquestrador em apps externos)

## Controles documentados

Detalhes técnicos de hardening: [`docs/security.md`](../docs/security.md).

## Licença

O projeto é **MIT**. Uso comercial e não comercial são permitidos; isso **não** reduz a importância de reportar falhas de segurança de forma responsável.
