"""Runtime-error handling for failed ReAct tool observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pineflow_agent.core.models import ActionPlan, AgentResult, Observation, ReActStep
from pineflow_agent.orchestration.event_stream import EventHandler, emit_event
from pineflow_agent.orchestration.agent.result_builder import failed_result

RuntimeErrorDecisionStatus = Literal["continue", "terminal"]


@dataclass(frozen=True)
class RuntimeErrorDecision:
    status: RuntimeErrorDecisionStatus
    result: AgentResult | None = None


@dataclass(frozen=True)
class RuntimeErrorRuntime:
    state: Any
    steps: list[ReActStep]
    session_id: str
    user_request: str
    on_event: EventHandler | None
    step_total: int
    auto_repair: bool

    def handle(self, plan: ActionPlan, observation: Observation) -> RuntimeErrorDecision:
        if self.auto_repair:
            emit_event(
                self.on_event,
                "retry",
                "工具执行失败；下一轮将基于这次错误反馈继续调整分析步骤。",
                session_id=self.session_id,
                step_index=len(self.steps),
                step_total=self.step_total,
                action=plan.action,
                error=observation.message,
            )
            return RuntimeErrorDecision("continue")

        result = failed_result(
            observation.message,
            steps=self.steps,
            state_tree=self.state.to_dict(),
            session_id=self.session_id,
        )
        emit_event(
            self.on_event,
            "failed",
            observation.message,
            session_id=self.session_id,
            result=result.to_dict(),
        )
        return RuntimeErrorDecision("terminal", result)
