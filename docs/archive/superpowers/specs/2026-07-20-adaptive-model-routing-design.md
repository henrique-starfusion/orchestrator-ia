# Design — Roteamento Adaptativo de Modelos (aprendizado por execução)

**Data:** 2026-07-20
**Status:** decisões fechadas com o usuário; implementação após Fase 2 (task envelope + validação)
**Objetivo:** o orquestrador aprende qual IA/modelo rende mais por `task_class` conforme executa, persiste esse aprendizado e o usa em rotas futuras.

## Decisões fechadas (com o usuário)

1. **Sinal v1 = exit code + score do validador.** Exit code (disponível hoje) alimenta desde já; score do loop de validação (Fase 2) domina quando existir.
2. **Autonomia = auto com guarda-corpos.** A rota muda sozinha só sob condições estritas (abaixo); toda mudança é logada com o porquê.
3. **Escopo = projeto + export global.** Stats vivem na memória do workspace (`.orchestrator/memory/strategies/`); `orchestrator stats --export` agrega pro perfil do usuário como seed de projetos novos.

## Modelo de sinal

Evento de outcome por despacho, chave `<task_class>|<client>|<model_key>`:

| Evento | score_event |
|---|---|
| Score do validador (Fase 2) | valor 0..1 do validador |
| Só exit code == success | 0.7 (teto — sucesso sem validação nunca supera evidência de validador) |
| Exit code != success | 0.0 |
| Escalação disparada (tier subiu) | 0.0 registrado para o modelo do tier inferior |

Agregação: **EMA** com `alpha = 0.3`; primeiro evento inicializa a EMA.

## Arquivo de stats — `.orchestrator/memory/strategies/model-stats.json`

```json
{
  "version": 1,
  "updated": "2026-07-20T12:00:00Z",
  "entries": {
    "docs|claude|sonnet": {
      "attempts": 12,
      "successes": 11,
      "failures": 1,
      "ema_score": 0.91,
      "last_used": "2026-07-20T11:58:00Z",
      "signals": { "exit": 12, "validator": 7 }
    }
  }
}
```

Modo no manifest: `generated` (nunca sobrescrito por update; nasce vazio).

## Guarda-corpos do override (Resolve-ModelRoute)

A rota default (task_map de `models.json`) só é substituída se TODAS as condições valem:

1. Candidatos = modelos do MESMO cliente nos tiers adjacentes (±1) + default. Sem comparação cross-client na v1.
2. Ambos (default e candidato) com `attempts >= 5`.
3. `ema(candidato) - ema(default) >= 0.15`.
4. Downgrade de tier é proibido quando o tier default é `deep` ou `max` (coerente com `never_downgrade_mid_critical_path` de models.json).
5. Salto máximo de 1 tier.

Quando override ocorre: `model-choice.json` ganha `learned: true`, `learned_reason: "ema docs|claude|opus 0.93 > sonnet 0.71 (n=8/7)"`, e a mesma linha vai pro console como `[APRENDIZADO] ...`.

## Integração

| Ponto | Mudança |
|---|---|
| `scripts/Update-ModelStats.ps1` (novo) | Recebe task_class/client/model_key/outcome(+score opcional); atualiza EMA e contadores; lock por retry simples (arquivo único, escrita atômica via temp+rename) |
| `scripts/Invoke-RoutedAgent.ps1` | Após execução, chama Update-ModelStats com exit outcome |
| Skill `validate-result` / loop Fase 2 | Chama Update-ModelStats com score; escalação registra 0.0 pro tier inferior |
| `scripts/Resolve-ModelRoute.ps1` | Lê stats, aplica guarda-corpos, loga override |
| `orchestrator stats` (novo comando) | Exibe tabela de EMAs; `--export` agrega pro perfil (`%USERPROFILE%\.orchestrator\model-stats-seed.json`); `--reset` zera stats do projeto |
| `orchestrator init` | Se seed global existe, importa como prior com peso reduzido (attempts contam ÷2, arredondado pra baixo) |

## Fora de escopo (v1)

- Algoritmos bandit/UCB — EMA + guarda-corpos basta; revisar se ruído aparecer.
- Comparação cross-client (claude vs codex) — exige normalização de score entre validadores; v2.
- Decaimento temporal além da EMA.

## Dependências

- Fase 2 (task envelope + validate-result) fornece o score; sem ela o aprendizado roda só com exit codes (teto 0.7) — funcional, porém conservador.
