"""Reparo determinístico de mojibake na ingestão de prompts (bug-049).

Prompt digitado num terminal Windows com codepage CP1252 chega com UTF-8
decodificado errado ("exigência" → "exigÃªncia"). Observado no caller=cursor
da GuardLine: o agente escreve o comando em UTF-8, o console decodifica em
CP1252 e o argv já chega corrompido — nenhum encoding downstream conserta.

O reparo é o round-trip clássico: re-encoda em CP1252 e decodifica em UTF-8.
Só aplica quando o texto tem o par assinatura de mojibake (Ã seguido de char
U+00A0–U+00BF) e o round-trip reduz esses pares — "NÃO"/"SÃO" legítimos não
casam a assinatura (Ã seguido de letra ASCII) e passam intactos.
"""

from __future__ import annotations

import re

_MOJIBAKE_PAIR_RE = re.compile("[ÂÃ][ -¿]")
_MAX_ROUNDS = 2  # mojibake duplo existe; triplo é teórico


def _markers(text: str) -> int:
    # No mojibake duplo a contagem de PARES não decresce a cada rodada
    # (4 marcadores em 2 pares → 2 em 2); a de marcadores Ã/Â decresce.
    return text.count("Ã") + text.count("Â")


def repair_mojibake(text: str) -> str:
    """Desfaz UTF-8-lido-como-CP1252; devolve o original se não for o caso."""
    if not text:
        return text
    current = text
    for _ in range(_MAX_ROUNDS):
        if not _MOJIBAKE_PAIR_RE.search(current):
            break
        try:
            candidate = current.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if _markers(candidate) >= _markers(current):
            break
        current = candidate
    return current
