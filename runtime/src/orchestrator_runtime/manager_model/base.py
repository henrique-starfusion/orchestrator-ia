"""Manager model: rules + LLM opcional."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from orchestrator_runtime.planning.analyzer import CriteriaBuilder, TaskAnalyzer
from orchestrator_runtime.routing.manager import RulesRouter
from orchestrator_runtime.tasks.models import (
    OrchestrationPlan,
    TaskAnalysis,
    TaskRecord,
)


class IterationDecision(BaseModel):
    action: str  # approve | correct | stop_incomplete | wait_user | fail
    reason: str
    issues: list[str] = Field(default_factory=list)
    score: float | None = None


class ManagerModel(Protocol):
    async def analyze_task(self, prompt: str, project_files: list[str] | None = None) -> TaskAnalysis: ...

    async def select_strategy(
        self,
        task: TaskRecord,
        analysis: TaskAnalysis,
        *,
        planner: str | None = None,
        executor: str | None = None,
        validator: str | None = None,
    ) -> OrchestrationPlan: ...

    async def evaluate_iteration(
        self,
        task: TaskRecord,
        validation: dict[str, Any],
        iteration: int,
    ) -> IterationDecision: ...


class RulesManager:
    def __init__(self, router: RulesRouter) -> None:
        self.analyzer = TaskAnalyzer()
        self.criteria = CriteriaBuilder()
        self.router = router

    async def analyze_task(
        self, prompt: str, project_files: list[str] | None = None
    ) -> TaskAnalysis:
        analysis = self.analyzer.analyze(prompt, project_files)
        analysis.acceptance_criteria = self.criteria.build(prompt, analysis)
        return analysis

    async def select_strategy(
        self,
        task: TaskRecord,
        analysis: TaskAnalysis,
        *,
        planner: str | None = None,
        executor: str | None = None,
        validator: str | None = None,
    ) -> OrchestrationPlan:
        return self.router.select_plan(
            task,
            analysis,
            planner=planner or task.constraints.planner,
            executor=executor or task.constraints.executor,
            validator=validator or task.constraints.validator,
        )

    async def evaluate_iteration(
        self,
        task: TaskRecord,
        validation: dict[str, Any],
        iteration: int,
    ) -> IterationDecision:
        status = validation.get("status")
        score = float(validation.get("score") or 0.0)
        blocking = validation.get("blocking_issues") or []
        threshold = 0.9
        if status == "approved" and score >= threshold and not blocking:
            return IterationDecision(
                action="approve", reason="validation approved", score=score
            )
        if iteration >= task.constraints.maximum_iterations:
            return IterationDecision(
                action="stop_incomplete",
                reason="maximum_iterations reached",
                issues=[i.get("id", str(i)) if isinstance(i, dict) else str(i) for i in blocking],
                score=score,
            )
        if blocking:
            return IterationDecision(
                action="correct",
                reason="blocking issues present",
                issues=[
                    i.get("id", "VAL") if isinstance(i, dict) else str(i) for i in blocking
                ],
                score=score,
            )
        if score < threshold:
            return IterationDecision(
                action="correct", reason="score below threshold", score=score
            )
        return IterationDecision(action="approve", reason="passed", score=score)


class LocalLlmManager:
    """Provider opcional OpenAI-compatible. Fallback para RulesManager se desabilitado/erro."""

    def __init__(self, rules: RulesManager, base_url: str, model: str, api_key: str | None) -> None:
        self.rules = rules
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    async def analyze_task(self, prompt: str, project_files: list[str] | None = None) -> TaskAnalysis:
        # MVP: usa rules; LLM hook preparado
        return await self.rules.analyze_task(prompt, project_files)

    async def select_strategy(
        self,
        task: TaskRecord,
        analysis: TaskAnalysis,
        *,
        planner: str | None = None,
        executor: str | None = None,
        validator: str | None = None,
    ) -> OrchestrationPlan:
        return await self.rules.select_strategy(
            task, analysis, planner=planner, executor=executor, validator=validator
        )

    async def evaluate_iteration(
        self,
        task: TaskRecord,
        validation: dict[str, Any],
        iteration: int,
    ) -> IterationDecision:
        return await self.rules.evaluate_iteration(task, validation, iteration)


def build_manager(config, router: RulesRouter):
    rules = RulesManager(router)
    if config.manager.provider == "openai-compatible" and config.manager.enabled:
        import os

        key = os.environ.get(config.manager.api_key_env)
        return LocalLlmManager(rules, config.manager.base_url, config.manager.model, key)
    return rules
