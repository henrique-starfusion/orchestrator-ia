"""Resources MCP somente leitura."""

from __future__ import annotations

import json
from typing import Any

from orchestrator_runtime.mcp.tools import OrchestratorMcpTools
from orchestrator_runtime.agents.process import redact


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


class OrchestratorMcpResources:
    def __init__(self, tools: OrchestratorMcpTools) -> None:
        self.tools = tools

    def list_uris(self) -> list[str]:
        return [
            "orchestrator://health",
            "orchestrator://agents",
            "orchestrator://tasks/{task_id}",
            "orchestrator://tasks/{task_id}/events",
            "orchestrator://tasks/{task_id}/plan",
            "orchestrator://tasks/{task_id}/result",
            "orchestrator://tasks/{task_id}/validation",
        ]

    def read(self, uri: str) -> str:
        if uri == "orchestrator://health":
            return _json(self.tools.health())
        if uri == "orchestrator://agents":
            return _json(self.tools.agents())
        prefix = "orchestrator://tasks/"
        if not uri.startswith(prefix):
            raise KeyError(uri)
        rest = uri[len(prefix) :]
        parts = rest.split("/")
        task_id = parts[0]
        if len(parts) == 1:
            return _json(self.tools.status({"task_id": task_id}))
        kind = parts[1]
        if kind == "events":
            return _json(self.tools.events({"task_id": task_id, "limit": 100}))
        if kind == "result":
            return _json(self.tools.result({"task_id": task_id}))
        if kind == "plan":
            service = self.tools._service()
            task = service.get(task_id)
            return _json({"task_id": task_id, "plan": task.plan})
        if kind == "validation":
            service = self.tools._service()
            task = service.get(task_id)
            return _json(
                {
                    "task_id": task_id,
                    "last_score": task.last_score,
                    "documentation": task.documentation_review,
                }
            )
        raise KeyError(uri)
