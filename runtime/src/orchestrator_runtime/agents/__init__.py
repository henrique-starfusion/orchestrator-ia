"""Registro de agentes e capabilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator_runtime.agents.base import AgentAdapter, AgentCapabilities, AgentStatus
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter, ProfileCliAdapter
from orchestrator_runtime.agents.process import CliExecutor
from orchestrator_runtime.config import RuntimeConfig

WORKER_ROLES = {"planner", "executor", "tester", "validator", "corrector"}

DEFAULT_CAPS: dict[str, AgentCapabilities] = {
    "claude": AgentCapabilities(
        roles=["planner", "executor", "validator", "corrector"],
        languages=["python", "typescript", "go"],
        can_write=True,
        can_validate=True,
    ),
    "codex": AgentCapabilities(
        roles=["executor", "corrector", "validator"],
        languages=["python", "typescript"],
        can_write=True,
        can_validate=True,
    ),
    "gemini": AgentCapabilities(
        roles=["planner", "executor", "validator"],
        experimental=True,
        can_write=True,
        can_validate=True,
    ),
    "kimi": AgentCapabilities(
        roles=["planner", "executor", "validator"],
        experimental=True,
        can_write=True,
        can_validate=True,
    ),
    "opencode": AgentCapabilities(
        roles=["executor", "planner", "validator"],
        experimental=True,
        can_write=True,
        can_validate=True,
    ),
}


class CursorClientAdapter(AgentAdapter):
    """Cursor é cliente IDE, não worker."""

    id = "cursor"
    kind = "ide-client"

    def detect(self) -> AgentStatus:
        return AgentStatus(
            id="cursor",
            available=False,
            kind="ide-client",
            verified=True,
            notes="Cursor e cliente do runtime; nao e executor CLI.",
        )

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            roles=[],
            can_write=False,
            can_validate=False,
            executable=False,
        )


class AgentRegistry:
    def __init__(self, config: RuntimeConfig, executor: CliExecutor | None = None) -> None:
        self.config = config
        self.executor = executor or CliExecutor(config.project_path)
        self._adapters: dict[str, AgentAdapter] = {}
        self._load()

    def _load(self) -> None:
        if self.config.fake_agents:
            for name in ("claude", "codex", "gemini", "kimi", "opencode"):
                self._adapters[name] = FakeAgentAdapter(name, self.config.project_path)
            self._adapters["cursor"] = CursorClientAdapter()
            return

        profiles_dir = self.config.profiles_dir
        if profiles_dir and profiles_dir.is_dir():
            for path in profiles_dir.glob("*.json"):
                profile = json.loads(path.read_text(encoding="utf-8"))
                agent_id = str(profile.get("id", path.stem))
                kind = str(profile.get("kind", "cli"))
                if agent_id == "cursor" or kind in {"ide-hint", "ide-client"}:
                    self._adapters["cursor"] = CursorClientAdapter()
                    continue
                caps = DEFAULT_CAPS.get(agent_id, AgentCapabilities())
                self._adapters[agent_id] = ProfileCliAdapter(
                    profile,
                    self.executor,
                    experimental=bool(caps.experimental or not profile.get("verified", False)),
                    capabilities=caps,
                )
        if "cursor" not in self._adapters:
            self._adapters["cursor"] = CursorClientAdapter()

    def get(self, agent_id: str) -> AgentAdapter | None:
        return self._adapters.get(agent_id)

    def list_statuses(self) -> list[AgentStatus]:
        return [a.detect() for a in self._adapters.values()]

    def available_workers(self, role: str) -> list[str]:
        result = []
        for agent_id, adapter in self._adapters.items():
            status = adapter.detect()
            caps = adapter.capabilities()
            if not status.available or not caps.executable:
                continue
            if role in caps.roles or role == "corrector" and "executor" in caps.roles:
                result.append(agent_id)
        return result

    def prefer_mvp_order(self, role: str, preferred: str | None = None) -> list[str]:
        available = self.available_workers(role)
        order = []
        if preferred and preferred in available:
            order.append(preferred)
        # MVP: Claude planeja/valida, Codex executa
        preferred_by_role = {
            "planner": ["claude", "codex", "opencode", "gemini", "kimi"],
            "executor": ["codex", "claude", "opencode", "gemini", "kimi"],
            "corrector": ["codex", "claude", "opencode", "gemini", "kimi"],
            "validator": ["claude", "codex", "opencode", "gemini", "kimi"],
        }
        for name in preferred_by_role.get(role, available):
            if name in available and name not in order:
                order.append(name)
        for name in available:
            if name not in order:
                order.append(name)
        return order
