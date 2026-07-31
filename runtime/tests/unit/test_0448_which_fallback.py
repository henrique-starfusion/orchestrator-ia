"""0.4.49 — detecção de CLI fora do PATH (bug-073).

kimi-code instalado via `npm i -g` num prefix fora do PATH do processo MCP
(npm-global do desktop): `which("kimi")` nunca achava, detect() marcava
indisponível e o roteador nunca escolhia kimi — "orquestrador não usa o
kimi mesmo instalado" (dono, 2026-07-30). which() agora faz fallback para
bins globais npm conhecidos (%APPDATA%\\npm e `npm prefix -g`).
"""

from __future__ import annotations

from pathlib import Path

import orchestrator_runtime.agents.process as proc


def _reset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "sem-nada"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(proc, "_NPM_BINS_CACHE", None)


def test_fallback_encontra_shim_no_appdata_npm(tmp_path, monkeypatch) -> None:
    _reset(monkeypatch, tmp_path)
    npm_dir = tmp_path / "appdata" / "npm"
    npm_dir.mkdir(parents=True)
    shim = npm_dir / "kimi.CMD"
    shim.write_text("@echo off\n", encoding="utf-8")

    found = proc.which("kimi")
    assert found is not None
    assert found.lower().endswith("kimi.cmd")


def test_fallback_preferencia_cmd_sobre_ps1(tmp_path, monkeypatch) -> None:
    _reset(monkeypatch, tmp_path)
    npm_dir = tmp_path / "appdata" / "npm"
    npm_dir.mkdir(parents=True)
    (npm_dir / "kimi.ps1").write_text("# ps1\n", encoding="utf-8")
    (npm_dir / "kimi.cmd").write_text("@echo off\n", encoding="utf-8")

    assert proc.which("kimi").lower().endswith(".cmd")


def test_fallback_retorna_none_quando_nao_existe(tmp_path, monkeypatch) -> None:
    _reset(monkeypatch, tmp_path)
    (tmp_path / "appdata" / "npm").mkdir(parents=True)
    assert proc.which("agente-inexistente-0448") is None


def test_cache_nao_recalcula_dirs(tmp_path, monkeypatch) -> None:
    _reset(monkeypatch, tmp_path)
    proc._npm_global_bins_nt()
    assert proc._NPM_BINS_CACHE is not None
