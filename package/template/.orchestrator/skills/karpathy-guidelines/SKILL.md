# Karpathy Guidelines (agent-agnostic)

Quatro princípios contra as falhas mais caras de LLMs codando, derivados das
observações públicas de Andrej Karpathy ("os modelos assumem errado e saem
rodando sem checar; supercomplicam; mudam código alheio como efeito
colateral"). Adaptado de github.com/multica-ai/andrej-karpathy-skills (MIT)
para valer para QUALQUER agente, não só Claude Code.

## 1. Pense antes de codar

Não assuma. Não esconda confusão. Apresente tradeoffs.

- Incerteza → pergunte, não adivinhe (ou use REQUIRES_INPUT se estiver numa
  task do orquestrador)
- Ambiguidade → apresente as interpretações possíveis antes de escolher
- Se existe abordagem mais simples, diga antes de implementar a complexa
- Se algo não faz sentido, NOMEIE a confusão em vez de disfarçar

## 2. Simplicidade primeiro

Mínimo código que resolve o problema. Nada especulativo.

- Sem features além do pedido
- Sem abstração para código de uso único
- Sem "flexibilidade"/"configurabilidade" não solicitada
- Sem tratamento de erro para cenários impossíveis
- Se 200 linhas podem ser 50, reescreva

Teste: um engenheiro sênior diria que está complicado demais? Simplifique.

## 3. Mudanças cirúrgicas

Toque só no necessário. Limpe só a SUA bagunça.

- Não "melhore" código, comentários ou formatação adjacentes
- Não refatore o que não está quebrado
- Combine o estilo existente, mesmo que faria diferente
- Viu código morto ALHEIO? Mencione — não delete
- Imports/variáveis/funções que A SUA mudança tornou órfãos: remova
- Código morto pré-existente: só com pedido explícito

Teste: cada linha alterada deve rastrear direto para o pedido do usuário.

## 4. Execução dirigida por objetivo

Critério de sucesso definido. Loope até verificar.

| Em vez de... | Transforme em... |
|---|---|
| "Adicione validação" | "Escreva testes para entradas inválidas, depois faça passar" |
| "Corrija o bug" | "Escreva o teste que reproduz, depois faça passar" |
| "Refatore X" | "Garanta testes verdes antes e depois" |

Tarefas multi-etapa: plano com verificação por etapa
(`1. [passo] → verifica: [checagem]`).

"LLMs são excepcionalmente bons em lupar até atingir objetivos específicos.
Não diga o que fazer — dê critérios de sucesso e observe." — Karpathy

## Nota de tradeoff

Cautela acima de velocidade. Para typo e one-liner óbvio, use julgamento —
nem toda mudança precisa do rigor completo. O alvo é erro caro em trabalho
não-trivial, não burocracia em tarefa simples.
