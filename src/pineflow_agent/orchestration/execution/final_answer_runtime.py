"""Final-answer result construction and event emission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pineflow_agent.core.models import ActionPlan, AgentResult, Observation, ReActStep
from pineflow_agent.orchestration.event_stream import EventHandler, emit_event
from pineflow_agent.orchestration.agent.goal_contract import attach_goal_contract
from pineflow_agent.orchestration.agent.result_quality_gate import (
    blocking_quality_message,
    evaluate_result_quality,
    has_blocking_findings,
    quality_gate_already_blocked,
)
from pineflow_agent.orchestration.agent.result_builder import completed_result


@dataclass(frozen=True)
class FinalAnswerRuntime:
    state_tree: dict[str, Any]
    steps: list[ReActStep]
    session_id: str
    on_event: EventHandler | None
    user_request: str = ""

    def complete_from_plan(
        self,
        plan: ActionPlan,
        *,
        emit_thought: bool = False,
        step_index: int = 0,
    ) -> AgentResult:
        final_message = str(plan.action_input.get("message") or "Task completed.")
        if emit_thought:
            emit_event(
                self.on_event,
                "thought",
                plan.thought or "Prepared the final answer.",
                session_id=self.session_id,
                step_index=step_index,
                thought=plan.thought,
            )
        result = completed_result(
            final_message,
            steps=self.steps,
            state_tree=self.state_tree,
            session_id=self.session_id,
        )
        attach_goal_contract(result, self.user_request)
        result.quality_findings = evaluate_result_quality(result)
        if has_blocking_findings(result.quality_findings) and not quality_gate_already_blocked(self.steps):
            message = blocking_quality_message(result.quality_findings)
            emit_event(
                self.on_event,
                "warning",
                message,
                session_id=self.session_id,
                step_index=step_index,
                action="final_answer",
                quality_findings=result.quality_findings,
            )
            self.steps.append(
                ReActStep(
                    index=len(self.steps) + 1,
                    thought=plan.thought,
                    action=plan.action,
                    action_input=dict(plan.action_input),
                    observation=Observation(
                        status="error",
                        message=message,
                        data={
                            "quality_findings": result.quality_findings,
                            "quality_gate_blocked": True,
                        },
                    ),
                )
            )
            return AgentResult(
                success=False,
                final_message=message,
                steps=self.steps,
                state=self.state_tree,
                session_id=self.session_id,
                status="quality_blocked",
                errors=[message],
                goal_contract=dict(result.goal_contract or {}),
                quality_findings=list(result.quality_findings or []),
            )
        emit_event(
            self.on_event,
            "summary",
            final_message,
            session_id=self.session_id,
            stream="stdout",
        )
        emit_event(
            self.on_event,
            "review",
            "Reviewed the final GIS state.",
            session_id=self.session_id,
            state_tree=self.state_tree,
            quality_findings=result.quality_findings,
        )
        emit_event(
            self.on_event,
            "completed",
            final_message,
            session_id=self.session_id,
            result=result.to_dict(),
        )
        return result
