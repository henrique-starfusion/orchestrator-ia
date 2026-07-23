"""Cursor MCP config merge/helpers — alinhado a Configure-CursorMcp.ps1."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SERVER_KEY = "orchestrator-ia"
LEGACY_SERVER_KEY = "multiagent-orchestrator"


def stdio_server_entry(command: str = "orchestrator") -> dict[str, Any]:
    """Entry canônica (Windows/Cursor): cmd /c + --project ${workspaceFolder}."""
    if os.name == "nt":
        return {
            "command": "cmd",
            "args": [
                "/c",
                command,
                "mcp",
                "serve",
                "--transport",
                "stdio",
                "--project",
                "${workspaceFolder}",
            ],
            "enabled": True,
        }
    return {
        "command": command,
        "args": [
            "mcp",
            "serve",
            "--transport",
            "stdio",
            "--project",
            "${workspaceFolder}",
        ],
        "enabled": True,
    }


def http_server_entry(url: str = "http://127.0.0.1:8765/mcp") -> dict[str, Any]:
    return {"url": url, "enabled": True}


def merge_mcp_json(
    existing: dict[str, Any] | None,
    *,
    transport: str = "stdio",
    command: str = "orchestrator",
    url: str | None = None,
) -> dict[str, Any]:
    """Merge sem destruir outros servidores ou credenciais."""
    root = dict(existing or {})
    servers = dict(root.get("mcpServers") or {})
    if transport == "http":
        servers[SERVER_KEY] = http_server_entry(url or "http://127.0.0.1:8765/mcp")
    else:
        servers[SERVER_KEY] = stdio_server_entry(command)
    servers.pop(LEGACY_SERVER_KEY, None)
    root["mcpServers"] = servers
    return root


def write_cursor_mcp_config(
    project_path: Path,
    *,
    transport: str = "stdio",
    command: str = "orchestrator",
    url: str | None = None,
) -> Path:
    """Escreve/mescla `.cursor/mcp.json` no projeto."""
    cursor_dir = project_path / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    path = cursor_dir / "mcp.json"
    existing = {}
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
    merged = merge_mcp_json(
        existing, transport=transport, command=command, url=url
    )
    path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def print_config(transport: str = "stdio", url: str | None = None) -> dict:
    return merge_mcp_json({}, transport=transport, url=url)
