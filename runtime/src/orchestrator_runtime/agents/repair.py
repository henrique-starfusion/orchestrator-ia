"""Reparo de CLI de agente quebrado (0.4.63).

Delega ao `scripts/Update-Agents.ps1`, que já carrega os mapas CURADOS de
instalação (`Get-AgentNpmPackageMap`, chocolatey, scoop, instalador nativo) e a
nota de segurança de nunca executar comando lido da saída do CLI. Recriar esses
mapas em Python seria manter duas listas divergindo em silêncio — e a segunda
cópia seria a que ninguém revisa.

Host sem PowerShell não é erro: devolve "reparo indisponível" e a task segue.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from orchestrator_runtime.agents.process import run_capture_file
from orchestrator_runtime.diagnostics import runtime_package_root


@dataclass
class RepairResult:
    ok: bool
    summary: str
    output: str = ""
    # False = nem dá para tentar neste host (sem PowerShell / sem o script).
    available: bool = True


def find_powershell() -> str | None:
    """PowerShell pelo PATH, com os fallbacks absolutos do bug-058.

    O processo MCP herda um PATH podado de alguns clientes IDE e `shutil.which`
    voltava vazio numa máquina com PowerShell instalado. Sysnative existe para o
    caso de um Python 32-bit enxergar o System32 redirecionado.
    """
    found = shutil.which("powershell") or shutil.which("powershell.exe")
    if found:
        return found
    if os.name != "nt":
        return shutil.which("pwsh")
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    for rel in (
        r"System32\WindowsPowerShell\v1.0\powershell.exe",
        r"Sysnative\WindowsPowerShell\v1.0\powershell.exe",
        r"SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
    ):
        candidate = Path(root) / rel
        if candidate.is_file():
            return str(candidate)
    return None


def update_agents_script() -> Path:
    """`scripts/Update-Agents.ps1` do pacote instalado."""
    return runtime_package_root().parent / "scripts" / "Update-Agents.ps1"


def repair_agent(
    agent_id: str, *, project_path: Path | str, timeout_s: int = 300
) -> RepairResult:
    """Reinstala UM agente. Nunca levanta: falha de reparo não derruba a task."""
    shell = find_powershell()
    script = update_agents_script()
    if shell is None or not script.is_file():
        missing = "PowerShell" if shell is None else f"script {script}"
        return RepairResult(
            False, "reparo indisponível", f"ausente: {missing}", available=False
        )

    command = [
        shell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ProjectPath",
        str(project_path),
        "-Only",
        agent_id,
        # -Force para os fallbacks npm/choco/scoop dispararem mesmo quando o
        # installation_method do detected.json está vazio — que é justamente o
        # estado de um CLI que a detecção reprovou.
        "-Force",
    ]
    # Captura em ARQUIVO, nunca PIPE: mesmo deadlock pós-kill do bug-059/bug-B.
    code, output = run_capture_file(command, cwd=project_path, timeout_s=timeout_s)
    ok = code == 0
    summary = (
        f"{agent_id}: reinstalação concluída"
        if ok
        else f"{agent_id}: reinstalação falhou (exit={code})"
    )
    return RepairResult(ok, summary, output[-4000:])
