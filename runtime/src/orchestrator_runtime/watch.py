"""Formatação do acompanhamento ao vivo de uma task (`orchestrator task watch`).

0.4.75 — antes disto, acompanhar uma task era cada sessão escrever o próprio laço
de shell. No trustsafe apareceram TRÊS laços `until ... sleep` vigiando a mesma
task (`c210252e2c58`), com `sleep` diferente em cada um — reescritos à mão porque o
pipe engolia a saída e o painel ficava mudo entre um ciclo e outro.

O runtime já tinha o material desde a 0.4.73: cada batida do heartbeat é um evento
com fase, idade da fase, `agent_active` e pid. Faltava transmitir.
"""

from __future__ import annotations

from typing import Any

# Evento que não acrescenta nada a quem está olhando: o heartbeat repete a mesma
# frase a cada 20-30s. Fica de fora por padrão e volta com `--verbose`.
RUIDO: tuple[str, ...] = ("loop_progress", "agent_progress")


def _hora(timestamp: str | None) -> str:
    """Só HH:MM:SS — a data é a mesma linha a linha e só rouba largura."""
    texto = str(timestamp or "")
    if "T" in texto:
        texto = texto.split("T", 1)[1]
    elif " " in texto:
        texto = texto.split(" ", 1)[1]
    return (texto.split(".")[0] or "--:--:--")[:8]


def format_event_line(evento: dict[str, Any]) -> str:
    """Uma linha por evento: hora, tipo, quem, e o resumo que o runtime já grava."""
    dados = evento.get("data") or {}
    quem = ""
    agente = evento.get("agent")
    papel = evento.get("role")
    if agente and papel:
        quem = f" {agente}/{papel}"
    elif agente or papel:
        quem = f" {agente or papel}"
    resumo = dados.get("summary") or dados.get("to") or ""
    if not resumo and dados.get("error"):
        resumo = f"erro: {dados['error']}"
    linha = f"[{_hora(evento.get('timestamp'))}] {evento.get('type')}{quem}"
    return f"{linha} — {resumo}" if resumo else linha


def format_live_line(live: dict[str, Any] | None) -> str:
    """A linha que responde "travou?" — idade do sinal e estado do pid."""
    if not live:
        return ""
    vivo = {True: "pid vivo", False: "pid MORTO", None: "pid ?"}.get(
        live.get("pid_alive"), "pid ?"
    )
    return (
        f"[VIVO] {live.get('summary') or live.get('phase')} "
        f"| sinal há {live.get('signal_age_s')}s | pid={live.get('pid')} {vivo}"
    )


def relevant(eventos: list[dict[str, Any]], *, verbose: bool) -> list[dict[str, Any]]:
    """Filtra o heartbeat repetitivo, salvo quando o dono pediu tudo."""
    if verbose:
        return list(eventos)
    return [e for e in eventos if e.get("type") not in RUIDO]
