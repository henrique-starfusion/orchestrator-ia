"""Orçamento de timeout por papel de agente.

0.4.79 — o orçamento tem DOIS EIXOS por papel (desenho adotado do
``TimeoutPolicy`` do LangGraph, ``libs/langgraph/langgraph/types.py``):

``run_timeout``
    Teto de relógio da tentativa. NUNCA renovado por sinal nenhum. É exatamente
    o número que existia até a 0.4.78 — um inteiro por papel.
``idle_timeout``
    Tempo máximo que a tentativa pode passar SEM progresso observável. Renovado
    pelo sinal que o runtime já emite (byte lido no stream, ou mudança no
    workspace via ``progress_probe``).

Com um eixo só, um agente que morreu mudo no segundo 5 e um agente que está
produzindo saída sem parar eram tratados IGUAL: os dois só morriam no teto.
``idle_timeout`` nulo = sem limite de ociosidade DESTE eixo; quem resolve o
sinal cai no ``agent_no_output_timeout_s`` global, que é o comportamento 0.4.78.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

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

# Eixo OCIOSO padrão, só onde ele muda alguma decisão.
#
# O número é FOLGADO de propósito. A referência é o `agent_no_output_timeout_s`
# global (900s, bug-086), que é o único valor desta frota já medido em produção
# sem matar trabalho legítimo. `executor` e `corrector` são os únicos papéis com
# teto duro de 2400s e os únicos que passam trechos longos lendo/pensando sem
# imprimir (o `claude -p` só imprime no fim), então ganham 900 + 300 = 1200s:
# 300s a mais que o global porque aqui o eixo ocioso é AUTORITATIVO para o papel,
# e o erro caro é matar quem estava trabalhando — enterrar um agente morto 300s
# depois custa 12% do teto duro dele; matar um agente vivo custa a task inteira.
# Papel sem entrada aqui não tem eixo ocioso próprio (nulo) e segue no global.
DEFAULT_IDLE_TIMEOUT_BY_ROLE: dict[str, int] = {
    "executor": 1200,
    "corrector": 1200,
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


@dataclass(frozen=True)
class AgentTimeoutPolicy:
    """Orçamento de UMA invocação de agente, nos dois eixos.

    ``idle_timeout_s`` nulo significa que este papel não declara eixo ocioso —
    NÃO significa "mate na hora". Quem aplica o eixo decide o fallback.
    """

    run_timeout_s: int
    idle_timeout_s: int | None = None


def _run_axis(value: Any) -> int | None:
    """Extrai o eixo DURO de um valor de papel (inteiro antigo ou dict novo)."""
    if isinstance(value, Mapping):
        raw = value.get("run_timeout", value.get("run_timeout_s"))
    else:
        raw = value
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _idle_axis(value: Any) -> int | None:
    """Extrai o eixo OCIOSO. Só o formato novo (dict) tem eixo ocioso."""
    if not isinstance(value, Mapping):
        return None  # formato antigo: inteiro é run_timeout, ocioso fica nulo
    raw = value.get("idle_timeout", value.get("idle_timeout_s"))
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None  # 0 = desligado, igual ao watchdog


def split_timeout_axes(
    raw_by_role: Any,
) -> tuple[dict[str, int], dict[str, int]]:
    """Separa ``agent_timeout_by_role`` cru nos dois eixos.

    Aceita os dois formatos na MESMA configuração::

        {"planner": 900,                                    # antigo
         "executor": {"run_timeout": 2400,                  # novo
                      "idle_timeout": 1200}}

    Devolve ``(run_by_role, idle_by_role)``. Um papel declarado como inteiro
    aparece só no primeiro — é isso que reproduz exatamente a 0.4.78 para quem
    não migrou o `policies.json`.
    """
    run_by_role: dict[str, int] = {}
    idle_by_role: dict[str, int] = {}
    if not isinstance(raw_by_role, Mapping):
        return run_by_role, idle_by_role
    for key, value in raw_by_role.items():
        role = str(key)
        run = _run_axis(value)
        if run is None:
            continue  # valor ilegível: o default do papel continua valendo
        run_by_role[role] = run
        idle = _idle_axis(value)
        if idle is not None:
            idle_by_role[role] = idle
    return run_by_role, idle_by_role


def minimum_task_budget_s(
    by_role: Mapping[str, Any] | None = None,
    *,
    default_s: int = DEFAULT_AGENT_TIMEOUT_S,
) -> int:
    """Piso do `maximum_duration_seconds`, derivado dos tetos DUROS dos papéis.

    Com os padrões dá 8700s (900+2400+600+1200+2400+1200) contra um
    `maximum_duration_seconds` de 3600: os próprios números do runtime se
    contradiziam. Toda task que realmente usasse o orçamento dos papéis morria no
    meio, sempre antes do validator — não era azar, era aritmética (bug-104).

    Piso, não teto: quem quiser mais voltas aumenta o `maximum_duration_seconds`.
    Teto é limite de paciência, não de qualidade — elevá-lo não faz task nenhuma
    demorar mais, só para de matar as que ainda estavam trabalhando.

    0.4.79 — só o eixo ``run_timeout`` entra nesta conta. O eixo ocioso não gasta
    orçamento: ele apenas interrompe mais cedo quem parou de dar sinal.
    """
    role_map: dict[str, int] = dict(DEFAULT_TIMEOUT_BY_ROLE)
    if by_role:
        for key, value in by_role.items():
            run = _run_axis(value)
            if run is not None:
                role_map[str(key)] = run
    return sum(
        max(0, int(role_map.get(role, default_s) or default_s))
        for role in _MINIMUM_PATH_ROLES
    )


def resolve_agent_timeout_policy(
    role: str,
    *,
    remaining_s: int,
    by_role: Mapping[str, Any] | None = None,
    idle_by_role: Mapping[str, Any] | None = None,
    default_s: int = DEFAULT_AGENT_TIMEOUT_S,
) -> AgentTimeoutPolicy:
    """Orçamento da invocação nos dois eixos.

    O eixo DURO é o de sempre: ``min(papel, restante)``, com a reserva do
    veredito descontada de quem gasta (bug-104) e piso ``MIN_AGENT_TIMEOUT_S``.
    Ele NUNCA é renovado — nem por sinal, nem por progresso.

    O eixo OCIOSO vem só do que a configuração declara para o papel (``by_role``
    no formato novo, ou ``idle_by_role`` explícito). Nulo = o papel não declara
    eixo ocioso; quem aplica cai no ``agent_no_output_timeout_s`` global.
    """
    run_map: dict[str, int] = dict(DEFAULT_TIMEOUT_BY_ROLE)
    idle_map: dict[str, int] = dict(DEFAULT_IDLE_TIMEOUT_BY_ROLE)
    if by_role:
        declared_run, declared_idle = split_timeout_axes(by_role)
        run_map.update(declared_run)
        for papel in declared_run:
            # Papel redeclarado no formato ANTIGO perde o eixo ocioso padrão:
            # inteiro puro é run_timeout e nada mais (compatibilidade 0.4.78).
            idle_map.pop(papel, None)
        idle_map.update(declared_idle)
    if idle_by_role:
        for key, value in idle_by_role.items():
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                idle_map[str(key)] = parsed
            else:
                idle_map.pop(str(key), None)

    role_budget = int(run_map.get(role, default_s) or default_s)
    remaining = max(0, int(remaining_s))
    idle = idle_map.get(role)
    if remaining < MIN_AGENT_TIMEOUT_S:
        # Orçamento esgotado: o caller encerra a tarefa; nada a ociosar.
        return AgentTimeoutPolicy(run_timeout_s=remaining, idle_timeout_s=idle)
    if role in _SPENDER_ROLES:
        remaining = max(MIN_AGENT_TIMEOUT_S, remaining - VERDICT_RESERVE_S)
    run = max(MIN_AGENT_TIMEOUT_S, min(role_budget, remaining))
    return AgentTimeoutPolicy(run_timeout_s=run, idle_timeout_s=idle)


def resolve_agent_timeout(
    role: str,
    *,
    remaining_s: int,
    by_role: Mapping[str, Any] | None = None,
    default_s: int = DEFAULT_AGENT_TIMEOUT_S,
) -> int:
    """Eixo DURO da invocação: ``min(papel, restante)``, com piso MIN.

    Quem executa não leva o orçamento todo: ``VERDICT_RESERVE_S`` fica para a
    validação (bug-104). A reserva nunca empurra o papel abaixo do piso — ela
    limita o teto, não cria orçamento onde não há.

    Se ``remaining_s < MIN_AGENT_TIMEOUT_S``, devolve ``remaining_s`` (pode ser 0)
    para o caller encerrar a tarefa por orçamento esgotado.
    """
    return resolve_agent_timeout_policy(
        role,
        remaining_s=remaining_s,
        by_role=by_role,
        default_s=default_s,
    ).run_timeout_s
