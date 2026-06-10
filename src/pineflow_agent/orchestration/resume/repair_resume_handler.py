"""Confirmed repair resume handler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pineflow_agent.core.models import ActionPlan, AgentResult, Observation, ReActStep, react_steps_from_payload
from pineflow_agent.core.state_tree import GISStateTree
from pineflow_agent.orchestration.agent.result_builder import completed_result, failed_result
from pineflow_agent.orchestration.event_stream import EventHandler
from pineflow_agent.orchestration.resume.resume_audit import (
    alias_repaired_layer_refs,
    append_observation_audit,
    confirmed_decision_audit,
    repair_audit,
    repair_input_snapshot,
    repair_steps_from_payload,
    repair_success_message,
    risk_message,
)
from pineflow_agent.orchestration.resume.resume_events import Emit, ResumeEventEmitter
from pineflow_agent.tools.contracts.tool_definitions import canonical_action_for_intent

ExecuteStep = Callable[..., Observation]
RunRequest = Callable[..., AgentResult]
KeyEventMessage = Callable[[str, dict[str, Any]], str]


@dataclass
class RepairResumeHandler:
    state: GISStateTree
    emit: Emit
    execute_action_step: ExecuteStep
    run_request: RunRequest
    key_event_message: Callable[..., str]

    def run_confirmed_repair(
        self,
        *,
        pending_task: dict,
        repair: dict,
        session_id: str = "",
        on_event: EventHandler | None = None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
    ) -> AgentResult:
        steps: list[ReActStep] = react_steps_from_payload(prior_steps)
        events = ResumeEventEmitter(self.emit, on_event, session_id=session_id)
        events.resume(
            "User confirmed the proposed GIS repair.",
            pending_task=pending_task,
            repair=repair,
        )

        repair_steps = repair_steps_from_payload(repair)
        patch = {key: value for key, value in dict(repair.get("patch") or {}).items() if value is not None}
        if not repair_steps and not patch:
            result = failed_result(
                "Confirmed repair has no executable action.",
                steps=steps,
                state_tree=self.state.to_dict(),
                session_id=session_id,
                errors=["Confirmed repair has no executable action."],
            )
            events.failed(result.final_message, result=result)
            return result

        step_total = len(steps) + len(repair_steps) + 1
        for repair_step in repair_steps:
            repair_plan = ActionPlan.from_dict(repair_step)
            before_snapshot = repair_input_snapshot(self.state, repair_plan)
            repair_observation = self.execute_action_step(
                repair_plan,
                index=len(steps) + 1,
                step_total=step_total,
                steps=steps,
                on_event=on_event,
                session_id=session_id,
            )
            if not repair_observation.is_success:
                result = failed_result(
                    repair_observation.message,
                    steps=steps,
                    state_tree=self.state.to_dict(),
                    session_id=session_id,
                )
                events.failed(repair_observation.message, result=result)
                return result
            audit = repair_audit(
                self.state,
                repair_plan,
                repair_observation,
                before_snapshot=before_snapshot,
                reason=risk_message(pending_task) or "用户确认后执行建议修复。",
                decision="user_confirmed_repair",
            )
            append_observation_audit(repair_observation, "audit_repairs", audit)
            append_observation_audit(repair_observation, "audit_decisions", confirmed_decision_audit(pending_task, repair=repair))
            events.repair_success(
                self.key_event_message(
                    "repair_success",
                    {"repair_audit": audit, "pending_task": pending_task, "repair": repair},
                    fallback=repair_success_message(audit),
                ),
                step_index=len(steps),
                step_total=step_total,
                action=repair_plan.action,
                repair_audit=audit,
            )

        original_action_input = dict(pending_task.get("filled_slots") or {})
        original_action_input.update(patch)
        alias_repaired_layer_refs(self.state, pending_task=pending_task, patch=patch)
        original_plan = ActionPlan(
            thought="Run the original GIS action after the confirmed repair.",
            action=canonical_action_for_intent(str(pending_task.get("active_intent") or ""), context=pending_task)
            or str(pending_task.get("active_intent") or "").strip(),
            action_input=original_action_input,
        )
        original_observation = self.execute_action_step(
            original_plan,
            index=len(steps) + 1,
            step_total=step_total,
            steps=steps,
            on_event=on_event,
            session_id=session_id,
        )
        if not original_observation.is_success:
            result = failed_result(
                original_observation.message,
                steps=steps,
                state_tree=self.state.to_dict(),
                session_id=session_id,
            )
            events.failed(original_observation.message, result=result)
            return result
        append_observation_audit(original_observation, "audit_decisions", confirmed_decision_audit(pending_task, repair=repair))

        continued_request = str(pending_task.get("original_request") or "").strip()
        if not continued_request:
            final_message = "Confirmed repair completed and the original GIS action finished."
            result = completed_result(
                final_message,
                steps=steps,
                state_tree=self.state.to_dict(),
                session_id=session_id,
            )
            events.completed(final_message, result=result)
            return result

        events.resume(
            "Confirmed repair completed; continuing the original GIS task.",
            pending_task=pending_task,
            original_request=continued_request,
        )
        return self.run_request(
            continued_request,
            session_id=session_id,
            on_event=on_event,
            prior_steps=steps,
        )
