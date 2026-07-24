"""Servidor MCP orchestrator-ia (transporte sobre TaskService)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from orchestrator_runtime.mcp.prompts import get_prompt, list_prompts
from orchestrator_runtime.mcp.resources import OrchestratorMcpResources
from orchestrator_runtime.mcp.tools import OrchestratorMcpTools


SERVER_NAME = "orchestrator-ia"


def build_tools(
    workspace: Path | None = None,
    *,
    fake_agents: bool | None = None,
) -> OrchestratorMcpTools:
    from orchestrator_runtime.config import resolve_default_workspace

    return OrchestratorMcpTools(
        default_workspace=resolve_default_workspace(workspace),
        fake_agents=fake_agents,
        verbose=False,
        mcp_wait_timeout_s=int(os.environ.get("ORCHESTRATOR_MCP_WAIT_TIMEOUT", "120")),
    )


def create_fastmcp_server(
    workspace: Path | None = None,
    *,
    fake_agents: bool | None = None,
):
    """Cria FastMCP server. Requer pacote mcp."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Pacote 'mcp' ausente. Instale: pip install 'mcp>=1.6,<2'"
        ) from exc

    tools = build_tools(workspace, fake_agents=fake_agents)
    resources = OrchestratorMcpResources(tools)
    mcp = FastMCP(SERVER_NAME)

    @mcp.tool(name="orchestrator_health")
    def orchestrator_health(workspace: str | None = None) -> dict[str, Any]:
        if workspace:
            return OrchestratorMcpTools(
                default_workspace=Path(workspace),
                fake_agents=fake_agents,
                verbose=False,
                mcp_wait_timeout_s=int(
                    os.environ.get("ORCHESTRATOR_MCP_WAIT_TIMEOUT", "120")
                ),
            ).health()
        return tools.health()

    @mcp.tool(name="orchestrator_analyze")
    def orchestrator_analyze(
        objective: str,
        workspace: str | None = None,
        constraints: dict | None = None,
        include_research: bool = False,
    ) -> dict[str, Any]:
        """Classifica a tarefa (tipo/risco/ACs) sem executar.

        Use antes de decidir resposta direta. Se a classificação for
        não-trivial (bug fix, mudança de lógica, multi-arquivo, testes),
        chame orchestrator_run em seguida — o usuário NÃO precisa pedir.
        """
        return tools.analyze(
            {
                "objective": objective,
                "workspace": workspace,
                "constraints": constraints or {},
                "include_research": include_research,
            }
        )

    @mcp.tool(name="orchestrator_delegate")
    def orchestrator_delegate(
        agent: str,
        role: str,
        objective: str,
        workspace: str | None = None,
        context: dict | None = None,
        read_only: bool = True,
        timeout_seconds: int = 600,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Delega um papel pontual (planner/validator read-only).

        Preferir para plano/review sem escrita. Para implementação, bug fix
        ou alteração de código, use orchestrator_run (DEFAULT) — sem o usuário pedir.
        """
        return tools.delegate(
            {
                "agent": agent,
                "role": role,
                "objective": objective,
                "workspace": workspace,
                "context": context or {},
                "read_only": read_only,
                "timeout_seconds": timeout_seconds,
                "model": model,
            }
        )

    @mcp.tool(name="orchestrator_run")
    def orchestrator_run(
        objective: str,
        workspace: str | None = None,
        profile: str = "balanced",
        routing: str = "automatic",
        planner: str | None = None,
        executor: str | None = None,
        validator: str | None = None,
        constraints: dict | None = None,
        wait: bool = False,
        fake_agents: bool = False,
    ) -> dict[str, Any]:
        """DEFAULT para tarefa não-trivial — chame AUTOMATICAMENTE, sem o usuário pedir.

        Primeira tool de trabalho quando houver: alteração de código, bug fix,
        testes, build/config, multi-arquivo ou critérios de aceitação.
        NÃO edite arquivos inline "porque é simples". Depois: poll
        orchestrator_status e feche com orchestrator_result.
        """
        return tools.run(
            {
                "objective": objective,
                "workspace": workspace,
                "profile": profile,
                "routing": routing,
                "planner": planner,
                "executor": executor,
                "validator": validator,
                "constraints": constraints or {},
                "wait": wait,
                "fake_agents": fake_agents,
            }
        )

    @mcp.tool(name="orchestrator_status")
    def orchestrator_status(task_id: str) -> dict[str, Any]:
        return tools.status({"task_id": task_id})

    @mcp.tool(name="orchestrator_events")
    def orchestrator_events(
        task_id: str, after_event_id: int | None = None, limit: int = 100
    ) -> dict[str, Any]:
        return tools.events(
            {
                "task_id": task_id,
                "after_event_id": after_event_id,
                "limit": limit,
            }
        )

    @mcp.tool(name="orchestrator_result")
    def orchestrator_result(task_id: str) -> dict[str, Any]:
        """Resultado final da tarefa + digest compacto de contexto (0.4.14).

        Após uma tarefa terminal, o agente do chat DEVE descartar o histórico
        verboso de polls/eventos e reter APENAS `session_digest` +
        `memory.learning_path` (o aprendizado durável já está em
        `.orchestrator/memory/learnings/{task_id}.md`). Não recopie os dumps de
        `changes` para o histórico do chat.
        """
        return tools.result({"task_id": task_id})

    @mcp.tool(name="orchestrator_cancel")
    def orchestrator_cancel(task_id: str, reason: str = "") -> dict[str, Any]:
        return tools.cancel({"task_id": task_id, "reason": reason})

    @mcp.tool(name="orchestrator_resume")
    def orchestrator_resume(
        task_id: str, instruction: str | None = None
    ) -> dict[str, Any]:
        return tools.resume({"task_id": task_id, "instruction": instruction})

    @mcp.tool(name="orchestrator_message")
    def orchestrator_message(task_id: str, message: str) -> dict[str, Any]:
        return tools.message({"task_id": task_id, "message": message})

    @mcp.tool(name="orchestrator_agents")
    def orchestrator_agents() -> dict[str, Any]:
        return tools.agents()

    @mcp.tool(name="orchestrator_memory_search")
    def orchestrator_memory_search(
        query: str,
        workspace: str | None = None,
        types: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return tools.memory_search(
            {
                "query": query,
                "workspace": workspace,
                "types": types or [],
                "limit": limit,
            }
        )

    @mcp.resource("orchestrator://health")
    def res_health() -> str:
        return resources.read("orchestrator://health")

    @mcp.resource("orchestrator://agents")
    def res_agents() -> str:
        return resources.read("orchestrator://agents")

    @mcp.resource("orchestrator://tasks/{task_id}")
    def res_task(task_id: str) -> str:
        return resources.read(f"orchestrator://tasks/{task_id}")

    @mcp.resource("orchestrator://tasks/{task_id}/events")
    def res_events(task_id: str) -> str:
        return resources.read(f"orchestrator://tasks/{task_id}/events")

    @mcp.resource("orchestrator://tasks/{task_id}/plan")
    def res_plan(task_id: str) -> str:
        return resources.read(f"orchestrator://tasks/{task_id}/plan")

    @mcp.resource("orchestrator://tasks/{task_id}/result")
    def res_result(task_id: str) -> str:
        return resources.read(f"orchestrator://tasks/{task_id}/result")

    @mcp.resource("orchestrator://tasks/{task_id}/validation")
    def res_validation(task_id: str) -> str:
        return resources.read(f"orchestrator://tasks/{task_id}/validation")

    for meta in list_prompts():

        def _make(name: str, template: str):
            @mcp.prompt(name=name)
            def _prompt() -> str:
                return template

            return _prompt

        _make(meta["name"], meta["template"])

    return mcp, tools


def serve(
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
    workspace: Path | None = None,
    fake_agents: bool | None = None,
) -> None:
    """Inicia o servidor MCP."""
    if host not in {"127.0.0.1", "localhost", "::1"} and os.environ.get(
        "ORCHESTRATOR_MCP_ALLOW_REMOTE"
    ) != "1":
        print(
            "[ERRO] Bind remoto bloqueado. Use 127.0.0.1 ou ORCHESTRATOR_MCP_ALLOW_REMOTE=1",
            file=sys.stderr,
        )
        raise SystemExit(2)

    mcp, _tools = create_fastmcp_server(workspace, fake_agents=fake_agents)
    if transport == "stdio":
        # Cursor marca stderr como [error]; silencia INFO do SDK e banner.
        import logging

        logging.getLogger("mcp").setLevel(logging.WARNING)
        logging.getLogger("mcp.server").setLevel(logging.WARNING)
        logging.getLogger("mcp.server.lowlevel").setLevel(logging.WARNING)
        # stdout só JSON-RPC — nenhum print/log em stdout
        mcp.run(transport="stdio")
        return
    print(
        f"[orchestrator-mcp] name={SERVER_NAME} transport={transport} host={host} port={port}",
        file=sys.stderr,
    )
    if transport in {"http", "streamable-http", "sse"}:
        # experimental HTTP
        try:
            mcp.run(transport="streamable-http", host=host, port=port)
        except TypeError:
            # older signature
            mcp.settings.host = host
            mcp.settings.port = port
            mcp.run(transport="sse")
        return
    raise SystemExit(f"transport desconhecido: {transport}")


def doctor(workspace: Path | None = None) -> dict:
    tools = build_tools(workspace)
    health = tools.health()
    try:
        import mcp as _mcp  # noqa: F401

        sdk = "installed"
    except ImportError:
        sdk = "missing"
    return {
        "sdk": sdk,
        "health": health,
        "prompts": [p["name"] for p in list_prompts()],
        "server_name": SERVER_NAME,
    }
