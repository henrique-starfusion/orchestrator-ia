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

# bug-097 — teto de EVIDÊNCIA. Marcador só vale em saída PEQUENA.
#
# Um CLI que não consegue nascer ou autenticar imprime centenas de bytes e morre.
# Um agente que RODOU imprime milhares — e o que ele imprime é conteúdo: código
# lido, prompt ecoado, documentação. Nas falhas de codex de 2026-08-07 o stderr
# trazia 20 KB do `tasks/service.py` deste próprio pacote, que contém as strings
# "codex login", "not logged in" e "unauthorized" porque é ONDE ELAS SÃO
# DEFINIDAS. O classificador leu a documentação do recurso como diagnóstico e
# devolveu `auth`; o problema real era `install`
# ("Missing optional dependency @openai/codex-win32-x64"). Resultado: o reparo
# automático que teria consertado NÃO rodou, e o dono recebeu um pedido de login
# que não resolvia nada.
#
# Custo aceito: um `rate limit` que só apareça depois de 8 KB de trabalho real
# deixa de ser classificado. É indistinguível de um agente citando a expressão —
# e classificar errado é pior que não classificar.
EVIDENCE_CAP_BYTES = 8192

# CLI ausente/corrompido/incompatível — reinstalar resolve.
INSTALL_MARKERS: tuple[str, ...] = (
    # Assinatura exata do codex quebrado no Windows (2026-08-07, frota inteira):
    # "Missing optional dependency @openai/codex-win32-x64. Reinstall Codex: ..."
    "missing optional dependency",
    "reinstall codex",
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

# bug-106 — CLI vivo e autenticado; quem falhou foi o SERVIÇO do outro lado.
# Nem reinstalar nem logar resolve: só esperar ou trocar de agente.
#
# Medido em 09/08 nos três `opencode` da frota (printbee 1, trustsafe 2): exit=1
# em ~2s com 165 bytes de `{"name":"UnknownError","message":"Unexpected server
# error. Check server logs for details.","ref":"err_..."}`. Sem estes marcadores
# a regra do fast-fail mudo classificava `install`, e o auto-reparo gastou uma
# reinstalação COMPLETA — que terminou `repair_ok: true` — para o agente falhar
# de novo, do mesmo jeito, na chamada seguinte.
SERVICE_MARKERS: tuple[str, ...] = (
    "unexpected server error",
    "unknownerror",
    "internal server error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "502 ",
    "503 ",
    "504 ",
    "overloaded_error",
    "server had an error",
    "upstream connect error",
)

# bug-109 — o processo NÃO NASCEU. NTSTATUS de falha de criação/inicialização:
# não há CLI a consertar nem credencial a renovar, a máquina não conseguiu
# spawnar. Reinstalar é pior que inútil aqui — a reinstalação também não nasce.
#
# Medido no trustsafe (task 22a07ed7e2de, 09/08 14:47): `corrector/codex` e
# `corrector/opencode` sairam `exit=3221225794` (0xC0000142
# STATUS_DLL_INIT_FAILED) em 0s com ZERO byte nos dois streams. O classificador
# caiu na regra do fast-fail mudo, devolveu `install`, e o auto-reparo tentou
# reinstalar os dois — e **a própria reinstalação falhou com o mesmo código**
# (`repair_ok: false, exit=3221225794`). Quatro lançamentos de processo falharam
# em ~1 segundo: o sinal era da máquina, não do CLI.
#
# Escopo estreito de propósito: só códigos de FALTA DE RECURSO/inicialização.
# Access violation (0xC0000005) e stack overrun (0xC0000409) ficam FORA — esses
# são crash de binário, onde reinstalar pode de fato resolver.
LAUNCH_FAILURE_EXIT_CODES: frozenset[int] = frozenset(
    {
        0xC0000142,  # STATUS_DLL_INIT_FAILED — DLL não inicializou
        0xC0000017,  # STATUS_NO_MEMORY
        0xC000012D,  # STATUS_COMMITMENT_LIMIT — sem memória virtual
        0xC0000018,  # STATUS_CONFLICTING_ADDRESSES
    }
)

# Duração acima da qual um NTSTATUS desses já não prova falha de lançamento:
# processo que trabalhou por minutos e só então morreu é outra história.
LAUNCH_FAILURE_MAX_S = 15.0


def is_launch_failure(exit_code: object, *, duration_s: float, produced: bool) -> bool:
    """Exit code de processo que nunca chegou a rodar (bug-109).

    Exige as três coisas juntas: código da família de recurso, morte
    praticamente imediata e nenhuma saída. Só o código não basta — o mesmo
    NTSTATUS pode aparecer num processo que já tinha trabalhado.
    """
    try:
        codigo = int(exit_code)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    # Windows reporta como unsigned; Python pode trazer o complemento negativo.
    if codigo < 0:
        codigo += 1 << 32
    return (
        codigo in LAUNCH_FAILURE_EXIT_CODES
        and duration_s <= LAUNCH_FAILURE_MAX_S
        and not produced
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
    """``"install"``, ``"auth"``, ``"service"``, ``"launch"`` ou ``None``.

    Regras duras, todas pagas com sangue:

    - ``timed_out`` → sempre ``None``. Quem passou do tempo estava VIVO; esse
      caminho já tem dono em ``_timeout_issue``. Reinstalar um CLI que trabalhou
      até o timeout é puro desperdício.
    - só classifica com ``status == "failed"`` — e é o **status**, não o
      ``exit_code`` cru: o profile do agente pode definir sucesso ≠ 0.
    - ``service`` vence tudo: erro do servidor do provedor não se conserta nem
      reinstalando nem logando, e a resposta certa é trocar de agente. Sem essa
      categoria o `opencode` caía na regra do fast-fail mudo e virava ``install``
      (bug-106).
    - ``auth`` vence ``install``: as saídas se sobrepõem ("npm error" aparece em
      log de login), e reinstalar por engano destrói a sessão do usuário.
    - marcador só vale em saída de até ``EVIDENCE_CAP_BYTES`` (bug-097): saída
      grande é conteúdo de um CLI que RODOU, e agente que lê código pode ecoar as
      próprias palavras-marcador.
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

    # bug-109 — antes de qualquer marcador: se o processo NÃO NASCEU, nada do
    # que está (ou não está) na saída diagnostica o CLI. Vem primeiro porque a
    # ausência de saída é justamente o que empurrava isto para `install`.
    if is_launch_failure(
        getattr(result, "exit_code", None),
        duration_s=float(getattr(result, "duration_s", 0.0) or 0.0),
        produced=bool(blob.strip()),
    ):
        return "launch"
    # bug-097 — só confia em marcador quando a saída é pequena o bastante para
    # SER um diagnóstico. Saída grande é conteúdo produzido por um CLI que rodou.
    if len(blob) <= EVIDENCE_CAP_BYTES:
        if any(marker in blob for marker in SERVICE_MARKERS):
            return "service"
        if any(marker in blob for marker in AUTH_MARKERS):
            return "auth"
        if any(marker in blob for marker in INSTALL_MARKERS):
            return "install"

    stdout = (getattr(result, "stdout", "") or "").strip()
    duration = float(getattr(result, "duration_s", 0.0) or 0.0)
    if not stdout and duration < fast_fail_s:
        return "install"
    return None
