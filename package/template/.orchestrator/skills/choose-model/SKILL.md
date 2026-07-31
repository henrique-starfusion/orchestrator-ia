# Choose Model

Escolher o agente e o modelo certos para cada tarefa no orquestrador —
camada de DECISÃO sobre a mecânica do `call-agent`. Fonte da verdade:
`config/models.json` do projeto (tiers, task_map por client). Esta skill é
o resumo operacional; em divergência, vale o arquivo.

## Regra de ouro

1. Classifique a tarefa (`task_class`): trivial, classify, docs,
   implementation, refactor_simple, code_review, tests, architecture,
   debugging_hard, security_review, complex_analysis, long_agentic,
   orchestration_plan.
2. Pegue o tier: `task_classes.<class>.tier` (fast < balanced < deep < max).
3. Escolha o client DISPONÍVEL no host (`orchestrator agents` — detect()
   real, não suposição) e aplique `clients.<client>.task_map[class]` →
   alias → `clients.<client>.models[alias]`.
4. Atalho que faz 1-3 de uma vez:
   `orchestrator route --task-class <class> --client <auto|claude|codex|kimi|gemini|opencode> --json`

## O que cada agente faz bem (observado na frota)

| Agente | Pontos fortes | Cuidados |
|---|---|---|
| claude | planner/validator mais estáveis (90% sucesso, ~100s); docs e análise | pendura em workspace sem trust (pré-aquecido no update) |
| codex | executor forte para implementação; sandbox próprio | shim .CMD: prompt >8KB só por stdin; sandbox workspace-write quebra no Windows (adapter troca) |
| kimi (k3) | contexto 1M tokens — monorepos, análises longas; executor/corrector provado em smoke | `-p` exige valor (sem stdin): prompt >8KB falha — escope o contexto; aliases reais `kimi-code/k3` |
| gemini | análise com contexto grande (quando instalado) | não bloquear orquestração se ausente |
| opencode | fallback genérico | QUARENTENA automática após 3 falhas rápidas (servidor pode estar fora) |
| cursor | front controller via MCP `orchestrator_*` | não é worker: não delegue execução a ele |

## Falha ≠ fim: cadeia de recuperação

1. Falha de spawn/serviço → o runtime rotaciona para o fallback do plano;
   3 falhas rápidas seguidas põem o agente em quarentena por 6h.
2. Timeout com progresso → iteração rejeitada como infra, corrector assume.
3. Score < 0.9 na validação → correction-loop até `maximum_iterations`.
4. Cota/crédito do modelo esgotado → o runtime marca o par (agent, model)
   como exausto neste run e rota sem ele.

## Erros comuns (todos já medidos na frota)

- Usar alias que não existe no host (`kimi-latest`, `gpt-5.6-sol-medium`
  onde só `gpt-5.6-sol` é aceito) → rota falha 100% das vezes. SEMPRE
  valide com `orchestrator route` ou `agents`.
- Mandar o repo inteiro no prompt ("contexto completo") → estouro de argv
  no .CMD + tokens desperdiçados. Escopo: arquivos tocados + brief curto.
- Escolher deep/max para docs ou typo — queima cota à toa; fast/balanced
  resolvem. Escale o tier só quando a validação falhar.
