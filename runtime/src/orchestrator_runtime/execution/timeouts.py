"""Orçamento de timeout por papel de agente."""

from __future__ import annotations

from typing import Mapping

# Mínimo para invocar um CLI; abaixo disso a tarefa deve expirar.
MIN_AGENT_TIMEOUT_S = 60

DEFAULT_AGENT_TIMEOUT_S = 1800

DEFAULT_TIMEOUT_BY_ROLE: dict[str, int] = {
    "planner": 900,
    "executor": 2400,
    "corrector": 2400,
    "validator": 1200,
    "tester": 600,
}

# bug-104 — papéis que GASTAM o orçamento da task. O veredito vem depois deles,
# e o orçamento só era conferido no topo da iteração: executor + corrector
# podiam consumir o `maximum_duration_seconds` inteiro e o validator chegava com
# `timeout_s=0`, matando a task por RuntimeError — falha com cara de mérito para
# um trabalho que talvez estivesse pronto.
_SPENDER_ROLES = frozenset({"executor", "corrector"})

# Fatia guardada para o veredito. Uma validação real desta frota leva ~7min;
# 600s cobre isso sem estrangular quem executa.
VERDICT_RESERVE_S = 600

# O percurso que o runtime SEMPRE pretende poder fazer: planejar, executar,
# testar, julgar, corrigir, julgar de novo. Rejeitar na primeira volta é o caso
# normal — `maximum_iterations` é 3 —, então o teto tem que caber a correção.
_MINIMUM_PATH_ROLES = (
    "planner",
    "executor",
    "tester",
    "validator",
    "corrector",
    "validator",
)


def minimum_task_budget_s(
    by_role: Mapping[str, int] | None = None,
    *,
    default_s: int = DEFAULT_AGENT_TIMEOUT_S,
) -> int:
    """Piso do `maximum_duration_seconds`, derivado dos tetos dos papéis.

    Com os padrões dá 8700s (900+2400+600+1200+2400+1200) contra um
    `maximum_duration_seconds` de 3600: os próprios números do runtime se
    contradiziam. Toda task que realmente usasse o orçamento dos papéis morria no
    meio, sempre antes do validator — não era azar, era aritmética (bug-104).

    Piso, não teto: quem quiser mais voltas aumenta o `maximum_duration_seconds`.
    Teto é limite de paciência, não de qualidade — elevá-lo não faz task nenhuma
    demorar mais, só para de matar as que ainda estavam trabalhando.
    """
    role_map = dict(DEFAULT_TIMEOUT_BY_ROLE)
    if by_role:
        for key, value in by_role.items():
            try:
                role_map[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
    return sum(
        max(0, int(role_map.get(role, default_s) or default_s))
        for role in _MINIMUM_PATH_ROLES
    )


def resolve_agent_timeout(
    role: str,
    *,
    remaining_s: int,
    by_role: Mapping[str, int] | None = None,
    default_s: int = DEFAULT_AGENT_TIMEOUT_S,
) -> int:
    """Retorna timeout da invocação: min(role, remaining), com piso MIN quando possible.

    Quem executa não leva o orçamento todo: ``VERDICT_RESERVE_S`` fica para a
    validação (bug-104). A reserva nunca empurra o papel abaixo do piso — ela
    limita o teto, não cria orçamento onde não há.

    Se ``remaining_s < MIN_AGENT_TIMEOUT_S``, devolve ``remaining_s`` (pode ser 0)
    para o caller encerrar a tarefa por orçamento esgotado.
    """
    role_map = dict(DEFAULT_TIMEOUT_BY_ROLE)
    if by_role:
        for key, value in by_role.items():
            try:
                role_map[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
    role_budget = int(role_map.get(role, default_s) or default_s)
    remaining = max(0, int(remaining_s))
    if remaining < MIN_AGENT_TIMEOUT_S:
        return remaining
    if role in _SPENDER_ROLES:
        remaining = max(MIN_AGENT_TIMEOUT_S, remaining - VERDICT_RESERVE_S)
    return max(MIN_AGENT_TIMEOUT_S, min(role_budget, remaining))
