"""Classificação de falha de CLI de agente (0.4.63).

Motivo: o `codex` saía exit=1 com ZERO byte em stdout, como executor E como
validator, em mais de um projeto (task 143e8b2ca47b: quem salvou foi o corrector
claude/opus). O `opencode` faz o mesmo nesta máquina. O bug-070 só colocava o
agente em quarentena — esconde o sintoma, não resolve a causa, e cada rodada
queimava orçamento antes de descobrir de novo.

Aqui só se CLASSIFICA. Quem repara é `agents/repair.py`; quem decide reparar é
`tasks/service.py`. As três categorias existem porque os remédios são OPOSTOS:
reinstalar um CLI que só está deslogado apaga a sessão e não conserta nada.
"""

from __future__ import annotations

from typing import Any

# CLI ausente/corrompido/incompatível — reinstalar resolve.
INSTALL_MARKERS: tuple[str, ...] = (
    "is not recognized",
    "command not found",
    "cannot find module",
    "module_not_found",
    "cannot find package",
    "enoent",
    "npm error",
    "npm err!",
    "winerror 2",
    "no such file or directory",
    "please reinstall",
    "unsupported version",
    "version is no longer supported",
)

# CLI vivo, faltando credencial — reinstalar NÃO resolve (e ainda apaga sessão).
AUTH_MARKERS: tuple[str, ...] = (
    "not logged in",
    "please log in",
    "codex login",
    "authentication failed",
    "unauthorized",
    "invalid api key",
    "missing api key",
    "session expired",
    "token expired",
    "quota exceeded",
    "rate limit",
    "insufficient_quota",
)

# Comando de login por agente. Genérico quando o agente não é conhecido: um
# palpite errado de comando é pior que dizer "veja a doc do CLI".
_AUTH_HINTS: dict[str, str] = {
    "codex": "codex login",
    "claude": "claude login",
    "opencode": "opencode auth login",
    "gemini": "gemini auth login",
    "kimi": "kimi login",
    "kimi-code": "kimi-code login",
    "cursor": "faça login pelo app do Cursor",
}


def auth_hint(agent_id: str) -> str:
    """Comando de autenticação do agente (nunca lido da saída do CLI)."""
    key = (agent_id or "").strip().lower()
    return _AUTH_HINTS.get(key, f"autentique o CLI '{agent_id}' (veja a doc do agente)")


def classify_agent_failure(
    result: Any, *, fast_fail_s: float = 90.0
) -> str | None:
    """``"install"``, ``"auth"`` ou ``None`` (mérito/inconclusivo).

    Regras duras, todas pagas com sangue:

    - ``timed_out`` → sempre ``None``. Quem passou do tempo estava VIVO; esse
      caminho já tem dono em ``_timeout_issue``. Reinstalar um CLI que trabalhou
      até o timeout é puro desperdício.
    - só classifica com ``status == "failed"`` — e é o **status**, não o
      ``exit_code`` cru: o profile do agente pode definir sucesso ≠ 0.
    - ``auth`` vence ``install``: as saídas se sobrepõem ("npm error" aparece em
      log de login), e reinstalar por engano destrói a sessão do usuário.
    - sem NENHUM marcador, só arrisca ``install`` quando o CLI morreu mudo e
      rápido (stdout vazio + duração < ``fast_fail_s``). Caso negativo que
      define o limite: o corrector da GuardLine (e0457603df65) rodou 17 min com
      20 KB de stderr e exit=1 — isso é mérito, não CLI quebrado.
    """
    if getattr(result, "timed_out", False):
        return None
    if getattr(result, "status", None) != "failed":
        return None

    blob = f"{getattr(result, 'stdout', '') or ''}\n{getattr(result, 'stderr', '') or ''}".lower()
    if any(marker in blob for marker in AUTH_MARKERS):
        return "auth"
    if any(marker in blob for marker in INSTALL_MARKERS):
        return "install"

    stdout = (getattr(result, "stdout", "") or "").strip()
    duration = float(getattr(result, "duration_s", 0.0) or 0.0)
    if not stdout and duration < fast_fail_s:
        return "install"
    return None
