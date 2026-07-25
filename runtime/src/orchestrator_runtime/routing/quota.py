"""Detecção de cota / rate-limit esgotada para fallback de modelo."""

from __future__ import annotations

import re
from typing import Any

# Marcadores comuns (Claude CLI, Anthropic API, Codex, OpenCode…).
_QUOTA_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\brate[\s_-]?limit",
        r"\btoo many requests\b",
        r"\b429\b",
        r"\bquota\b",
        r"\busage[\s_-]?limit",
        r"\bexceeded\b.*\b(limit|quota|usage|cap)\b",
        r"\b(limit|quota|usage|cap)\b.*\bexceeded\b",
        r"\bout of credits?\b",
        r"\bcredit balance\b",
        r"\bspending limit\b",
        r"\boverloaded\b",
        r"\bmodel.*(unavailable|not available|capacity)\b",
        r"\btemporarily unavailable\b",
        r"\bcapacity\b.*\b(exceeded|exhausted)\b",
        r"\bexhausted\b.*\b(quota|usage|limit)\b",
        r"\byou.?ve hit\b.*\b(limit|cap|quota)\b",
        r"\bhit your (usage|rate|spending)",
    )
)


def is_model_quota_exhausted(
    *,
    status: str | None = None,
    exit_code: int | None = None,
    stdout: str = "",
    stderr: str = "",
) -> bool:
    """True se a falha indica cota/rate-limit do modelo (vale tentar o próximo)."""
    blob = f"{stdout or ''}\n{stderr or ''}"
    if any(p.search(blob) for p in _QUOTA_PATTERNS):
        return True
    # Exit codes comuns de rate-limit / payment em CLIs
    if exit_code in {429, 402}:
        return True
    return False


def should_retry_next_model(result: Any) -> bool:
    """Wrapper para AgentResult-like."""
    return is_model_quota_exhausted(
        status=getattr(result, "status", None),
        exit_code=getattr(result, "exit_code", None),
        stdout=getattr(result, "stdout", "") or "",
        stderr=getattr(result, "stderr", "") or "",
    )
