"""Roteamento task → strategy → role → agent → model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.config import RuntimeConfig
from orchestrator_runtime.tasks.models import OrchestrationPlan, TaskAnalysis, TaskRecord


@dataclass
class RoleAssignment:
    role: str
    agent: str
    model: str | None = None
    model_flag: str | None = None
    reason: str = ""


class CapabilityScorer:
    def score(self, agent_id: str, role: str, analysis: TaskAnalysis) -> float:
        base = {
            "claude": 0.9,
            "codex": 0.85,
            "opencode": 0.6,
            "gemini": 0.55,
            "kimi": 0.5,
        }.get(agent_id, 0.4)
        if role == "planner" and agent_id == "claude":
            base += 0.05
        if role == "executor" and agent_id == "codex":
            base += 0.05
        if "python" in analysis.languages and agent_id in {"claude", "codex"}:
            base += 0.02
        return min(base, 1.0)


class RulesRouter:
    def __init__(self, config: RuntimeConfig, registry: AgentRegistry) -> None:
        self.config = config
        self.registry = registry
        self.scorer = CapabilityScorer()

    def select_plan(
        self,
        task: TaskRecord,
        analysis: TaskAnalysis,
        *,
        planner: str | None = None,
        executor: str | None = None,
        validator: str | None = None,
    ) -> OrchestrationPlan:
        planner_id = self._pick("planner", analysis, planner)
        executor_id = self._pick("executor", analysis, executor)
        validator_id = self._pick("validator", analysis, validator)
        # Independent validation obrigatória quando a policy exige
        if (
            self.config.limits.require_independent_validation
            and validator_id == executor_id
        ):
            alts = self.registry.prefer_mvp_order("validator")
            swapped = False
            for alt in alts:
                if alt != executor_id:
                    validator_id = alt
                    swapped = True
                    break
            if not swapped:
                raise RuntimeError(
                    "require_independent_validation: nenhum validator disponivel "
                    f"diferente do executor ({executor_id})"
                )
        fallbacks = {
            "executor": [a for a in self.registry.prefer_mvp_order("executor") if a != executor_id][:2],
            "validator": [a for a in self.registry.prefer_mvp_order("validator") if a != validator_id][:2],
            "planner": [a for a in self.registry.prefer_mvp_order("planner") if a != planner_id][:2],
        }
        return OrchestrationPlan(
            strategy="execute_review_repair",
            planner=planner_id,
            executor=executor_id,
            tester="runtime",
            validator=validator_id,
            fallbacks=fallbacks,
            maximum_iterations=task.constraints.maximum_iterations,
            roles={
                "orchestrator": "runtime",
                "planner": planner_id,
                "executor": executor_id,
                "tester": "runtime",
                "validator": validator_id,
            },
        )

    def _pick(self, role: str, analysis: TaskAnalysis, preferred: str | None) -> str:
        if preferred == "cursor":
            raise ValueError("Cursor nao pode ser selecionado como worker")
        candidates = self.registry.prefer_mvp_order(role, preferred)
        if not candidates:
            raise RuntimeError(f"Nenhum agente disponivel para papel {role}")
        ranked = sorted(
            candidates,
            key=lambda a: self.scorer.score(a, role, analysis),
            reverse=True,
        )
        if preferred and preferred in ranked:
            return preferred
        return ranked[0]

    def resolve_model(
        self,
        agent_id: str,
        task_type: str,
        role: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Retorna (model_or_alias, model_flag). Se não confirmado, (None, None).

        ``role`` permite override por papel (ex.: planner → fable/opus quando
        configurados no cliente), independentemente do ``task_type``.
        """
        clients = (self.config.models or {}).get("clients") or {}
        client = clients.get(agent_id) or {}
        model_flag = client.get("model_flag")
        flag = str(model_flag) if model_flag else None

        # Preferências por papel (planner prefere fable → opus quando disponíveis).
        for token in self._role_model_candidates(agent_id, role, client):
            resolved = self._materialize_model_token(client, token, flag)
            if resolved[0] is not None:
                return resolved

        task_map = client.get("task_map") or {}
        alias = task_map.get(task_type)
        if not alias:
            # map complexity-ish defaults
            tier_map = {
                "docs": "balanced",
                "documentation": "balanced",
                "implementation": "balanced",
                "architecture": "deep",
                "complex_analysis": "max",
            }
            tier = (self.config.models.get("task_classes") or {}).get(task_type, {}).get(
                "tier"
            ) or tier_map.get(task_type, "balanced")
            aliases = client.get("aliases") or {}
            alias = aliases.get(tier)
        if not alias:
            return None, None
        return self._materialize_model_token(client, str(alias), flag)

    def _role_model_candidates(
        self, agent_id: str, role: str | None, client: dict[str, Any]
    ) -> list[str]:
        if not role:
            return []
        prefs = (self.config.models or {}).get("role_model_preferences") or {}
        # Defaults do produto: planner Claude → Fable 5, senão Opus 4.8
        defaults: dict[str, dict[str, list[str]]] = {
            "planner": {
                "claude": ["fable", "opus"],
                "cursor": ["max", "deep"],
            }
        }
        by_role = prefs.get(role) if isinstance(prefs.get(role), dict) else None
        if by_role is None:
            by_role = defaults.get(role) or {}
        raw = by_role.get(agent_id) if isinstance(by_role, dict) else None
        if not isinstance(raw, list):
            return []
        models = client.get("models") or {}
        aliases_map = client.get("aliases") or {}
        alias_values = {str(v) for v in aliases_map.values()}
        out: list[str] = []
        for item in raw:
            token = str(item)
            # "disponível" = declarado no cliente (alias CLI ou chave em models/aliases)
            if (
                token in models
                or token in aliases_map
                or token in alias_values
            ):
                out.append(token)
        return out

    def _materialize_model_token(
        self,
        client: dict[str, Any],
        alias: str,
        flag: str | None,
    ) -> tuple[str | None, str | None]:
        models = client.get("models") or {}
        aliases_map = client.get("aliases") or {}
        # task_map / prefs podem apontar para alias de CLI (sonnet/fable) ou tier (balanced).
        token = str(alias)
        if token in aliases_map:
            token = str(aliases_map[token])
        prefer_aliases = bool(client.get("prefer_aliases", True))
        if prefer_aliases:
            # Codex-like: sem mapa de aliases, keys de models são tiers → concreto.
            alias_names = {str(v) for v in aliases_map.values()}
            if token in models and token not in alias_names and not aliases_map:
                return str(models[token]), flag
            return token, flag
        concrete = models.get(token, models.get(str(alias), token))
        return str(concrete), flag
