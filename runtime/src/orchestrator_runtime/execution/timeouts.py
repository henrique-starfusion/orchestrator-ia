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


def resolve_agent_timeout(
    role: str,
    *,
    remaining_s: int,
    by_role: Mapping[str, int] | None = None,
    default_s: int = DEFAULT_AGENT_TIMEOUT_S,
) -> int:
    """Retorna timeout da invocação: min(role, remaining), com piso MIN quando possible.

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
    return max(MIN_AGENT_TIMEOUT_S, min(role_budget, remaining))
