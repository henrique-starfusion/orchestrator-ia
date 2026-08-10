"""Roteamento task → strategy → role → agent → model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.callers import caller_profile, detect_caller
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
            # 0.4.70 — 0.6 era um palpite, e a produção discordou: `opencode`
            # fechou 0/3 (printbee 0/1, trustsafe 0/2) depois de o auto-reparo
            # tê-lo REINSTALADO com sucesso. Reinstalar não é o remédio dele, e
            # como fallback ele queimava uma rodada por task em que era chamado.
            # Abaixo de 0.4 (o valor de agente desconhecido) de propósito:
            # desconhecido ainda pode funcionar, este já provou que não.
            "opencode": 0.3,
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
        # 0.4.29 — o CLI que ja esta atendendo o usuario nao deve virar executor
        # sem necessidade: disputa cota/rate limit do mesmo provedor e concentra
        # o risco num agente so. Override explicito do usuario sempre vence.
        busy = caller_profile(detect_caller()).busy_agent

        planner_id = self._pick("planner", analysis, planner)
        executor_id = self._pick("executor", analysis, executor, avoid=busy)
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

    def _pick(
        self,
        role: str,
        analysis: TaskAnalysis,
        preferred: str | None,
        *,
        avoid: str | None = None,
    ) -> str:
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
        # 'avoid' e preferencia, nunca restricao: se for o unico disponivel, usa.
        if avoid:
            alternatives = [a for a in ranked if a != avoid]
            if alternatives:
                return alternatives[0]
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
        candidates = self.resolve_model_candidates(agent_id, task_type, role=role)
        if not candidates:
            return None, None
        return candidates[0]

    def resolve_model_candidates(
        self,
        agent_id: str,
        task_type: str,
        role: str | None = None,
    ) -> list[tuple[str | None, str | None]]:
        """Lista ordenada de (model, flag) — melhor primeiro; para fallback de cota.

        Planner Claude (0.4.25+): fable → opus → sonnet. Em esgotamento do
        melhor modelo, o runtime tenta o próximo da lista.
        """
        clients = (self.config.models or {}).get("clients") or {}
        client = clients.get(agent_id) or {}
        model_flag = client.get("model_flag")
        flag = str(model_flag) if model_flag else None

        out: list[tuple[str | None, str | None]] = []
        seen: set[str] = set()

        def _add(token: str | None) -> None:
            if token is None:
                return
            resolved = self._materialize_model_token(client, str(token), flag)
            if resolved[0] is None:
                return
            key = str(resolved[0])
            if key in seen:
                return
            seen.add(key)
            out.append(resolved)

        for token in self._role_model_candidates(agent_id, role, client):
            _add(token)

        # Fallback task_map / tier se prefs vazias ou como último candidato
        task_map = client.get("task_map") or {}
        alias = task_map.get(task_type)
        if not alias:
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
        if alias:
            _add(str(alias))

        return out

    def _role_model_candidates(
        self, agent_id: str, role: str | None, client: dict[str, Any]
    ) -> list[str]:
        if not role:
            return []
        prefs = (self.config.models or {}).get("role_model_preferences") or {}
        # Defaults do produto (0.4.25):
        # - planner (Claude instalado): Fable → Opus → Sonnet (cota/esgotamento)
        # - executor/corrector: modelos fortes para código (Opus / gpt-5.6-sol)
        # - validator: intermediário (Sonnet / balanced)
        defaults: dict[str, dict[str, list[str]]] = {
            "planner": {
                "claude": ["fable", "opus", "sonnet"],
                "cursor": ["max", "deep"],
            },
            "executor": {
                "claude": ["opus", "sonnet"],
                "codex": ["deep", "balanced", "gpt-5.6-sol"],
                "opencode": ["deep", "balanced"],
                "cursor": ["deep", "max"],
            },
            "corrector": {
                "claude": ["opus", "sonnet"],
                "codex": ["deep", "balanced", "gpt-5.6-sol"],
                "opencode": ["deep", "balanced"],
                "cursor": ["deep", "max"],
            },
            "validator": {
                "claude": ["sonnet", "haiku"],
                "codex": ["balanced", "fast"],
                "opencode": ["balanced", "fast"],
                "cursor": ["balanced", "fast"],
            },
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
