"""Identidade de processo do S.O. — base da ceifa de CLI orfao (bug-119).

O executor rastreava os CLIs lancados num set EM MEMORIA
(`CliExecutor._active_pids`), lido so por `kill_active()` no cancelamento
ordenado. Orfao e, por definicao, o caso em que o rastreador ja se foi: se o
runtime morre por crash, `taskkill`, restart do editor ou fim abrupto do
terminal, o set morre junto e os CLIs seguem vivos sem que nenhum codigo do
orquestrador saiba que existem. Medido em 11/08 nesta maquina: 338 processos
entre node, cmd, conhost e python, com o teto de recurso fazendo qualquer
PowerShell falhar com `exit=-1073741502` (0xC0000142) antes da primeira linha.

Rastrear so o numero do PID nao resolve — resolveria PIOR. O Windows recicla
numero de processo, entao matar por numero e destrutivo: o alvo pode ser um
programa alheio que herdou o mesmo numero. A identidade util e
`(nome da imagem, instante de criacao)`, lida do PROPRIO S.O.:

- Windows: `GetProcessTimes` (ftCreationTime) + `QueryFullProcessImageNameW`.
- Linux: `/proc/<pid>/stat` — campo 2 (`comm`) e campo 22 (`starttime`).
- Resto: sem leitor confiavel, `process_identity` devolve `None`, e sem
  identidade NENHUM processo e morto. Falhar para o lado de nao matar e a
  unica assimetria aceitavel aqui.

Sem daemon, sem thread e sem processo novo: este modulo so LE identidade. Quem
decide e mata e `TaskService._reap_orphan_agents`, chamado dos pontos de poll
que ja existiam (bug-085/bug-113).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Diferenca entre a epoca do FILETIME (1601-01-01) e a do Unix (1970-01-01).
_FILETIME_EPOCH_DELTA_S = 11_644_473_600.0
# Folga na comparacao do instante de criacao. O valor persiste em coluna Float
# do SQLite e volta identico; a folga cobre arredondamento de roundtrip, nao
# reuso de PID — reuso separa os instantes por ordens de magnitude a mais.
IDENTITY_TOLERANCE_S = 1.0


@dataclass(frozen=True)
class ProcessIdentity:
    """Quem o PID e AGORA, segundo o sistema operacional."""

    image: str
    create_time: float


def process_identity(pid: int) -> ProcessIdentity | None:
    """Identidade atual do PID, ou ``None`` se ele nao existe / nao da para ler."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if os.name == "nt":
        return _identity_windows(pid)
    return _identity_proc(pid)


def identity_matches(
    recorded_image: str | None,
    recorded_create_time: float | None,
    current: ProcessIdentity | None,
    *,
    tolerance_s: float = IDENTITY_TOLERANCE_S,
) -> bool:
    """O PID de hoje e o MESMO processo que registramos? Os dois campos ou nada."""
    if current is None:
        return False
    if not recorded_image or recorded_create_time is None:
        return False
    if str(recorded_image).strip().lower() != current.image.strip().lower():
        return False
    try:
        delta = abs(float(recorded_create_time) - float(current.create_time))
    except (TypeError, ValueError):
        return False
    return delta <= max(0.0, float(tolerance_s))


def _identity_windows(pid: int) -> ProcessIdentity | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    # PROCESS_QUERY_LIMITED_INFORMATION: o menor direito que responde as duas
    # perguntas e que funciona sem elevacao para processo do proprio usuario.
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        criacao = wintypes.FILETIME()
        saida = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        usuario = wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(criacao),
            ctypes.byref(saida),
            ctypes.byref(kernel),
            ctypes.byref(usuario),
        )
        if not ok:
            return None
        tamanho = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(tamanho.value)
        ok = kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(tamanho)
        )
        if not ok:
            return None
        bruto = (criacao.dwHighDateTime << 32) | criacao.dwLowDateTime
        instante = bruto / 10_000_000.0 - _FILETIME_EPOCH_DELTA_S
        return ProcessIdentity(
            image=os.path.basename(buffer.value).lower(), create_time=instante
        )
    except OSError:
        return None
    finally:
        kernel32.CloseHandle(handle)


def _identity_proc(pid: int) -> ProcessIdentity | None:
    """Linux: `/proc/<pid>/stat`. O `starttime` e em ticks desde o boot.

    Comparar ticks contra ticks e o mesmo contrato do Windows: numero estavel
    enquanto o processo vive, diferente para qualquer processo que herde o PID
    depois. Nao ha razao para converter para epoca — a conversao precisaria do
    boot time e so acrescentaria erro.
    """
    try:
        bruto = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fim_comm = bruto.rfind(")")
    inicio_comm = bruto.find("(")
    if fim_comm < 0 or inicio_comm < 0 or fim_comm < inicio_comm:
        return None
    comm = bruto[inicio_comm + 1 : fim_comm]
    campos = bruto[fim_comm + 1 :].split()
    # `campos[0]` e o campo 3 (state); `starttime` e o campo 22 -> indice 19.
    if len(campos) < 20:
        return None
    try:
        starttime = float(campos[19])
    except ValueError:
        return None
    return ProcessIdentity(image=comm.strip().lower(), create_time=starttime)
