"""Validation and execution for resumed pending GIS actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pineflow_agent.core.models import ActionPlan, AgentResult, Observation, ReActStep, react_steps_from_payload
from pineflow_agent.core.state_tree import GISStateTree
from pineflow_agent.orchestration.agent.result_builder import awaiting_result, completed_result, failed_result
from pineflow_agent.orchestration.event_stream import EventHandler
from pineflow_agent.orchestration.hooks.contexts import HookPoint, ToolContext
from pineflow_agent.orchestration.hooks.pipeline import HookPipeline
from pineflow_agent.orchestration.resume.resume_audit import append_observation_audit, resume_decision_audit
from pineflow_agent.orchestration.resume.validation_gate import pending_choices_from_context
from pineflow_agent.risks.converters import risks_from_issues
from pineflow_agent.risks.policy import RiskPolicy
from pineflow_agent.rules.validation import PendingTask, ValidationIssue, allowed_resume_actions
from pineflow_agent.tools.registry.tool_registry import ToolRegistry
from pineflow_agent.tools.semantic.semantic_tools import normalize_semantic_input

Emit = Callable[..., None]
ExecuteStep = Callable[..., Observation]
PendingTaskFactory = Callable[..., PendingTask]


@dataclass
class ResumedPlanExecutor:
    state: GISStateTree
    emit: Emit
    execute_action_step: ExecuteStep
    pending_task_from_issue: PendingTaskFactory
    tool_registry: ToolRegistry
    hooks: HookPipeline

    def validate_or_execute(
        self,
        plan: ActionPlan,
        *,
        pending_task: dict,
        original_request: str,
        session_id: str,
        on_event: EventHandler | None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
    ) -> AgentResult:
        steps: list[ReActStep] = react_steps_from_payload(prior_steps)
        if plan.action == "final_answer":
            final_message = str(plan.action_input.get("message") or "Task completed.")
            result = completed_result(
                final_message,
                steps=steps,
                state_tree=self.state.to_dict(),
                session_id=session_id,
            )
            self.emit(on_event, "completed", final_message, session_id=session_id, result=result.to_dict())
            return result

        tool_ctx = ToolContext(plan=plan, state=self.state, tool_registry=self.tool_registry)
        tool_ctx = self.hooks.emit(HookPoint.BEFORE_TOOL_CALL, tool_ctx)
        validation_issues = list(tool_ctx.all_validation_issues())
        if validation_issues:
            primary_issue = validation_issues[0]
            event = "repair" if primary_issue.stage == "preflight" else "question"
            return self._pause_resumed_plan(
                plan,
                issues=validation_issues,
                pending_task=pending_task,
                original_request=original_request,
                session_id=session_id,
                on_event=on_event,
                event=event,
                prior_steps=steps,
            )
        observation = self.execute_action_step(
            plan,
            index=len(steps) + 1,
            step_total=max(len(steps) + 1, 1),
            steps=steps,
            on_event=on_event,
            session_id=session_id,
            preflight_warnings=list(tool_ctx.preflight_warnings or []),
        )
        if not observation.is_success:
            result = failed_result(
                observation.message,
                steps=steps,
                state_tree=self.state.to_dict(),
                session_id=session_id,
            )
            self.emit(on_event, "failed", observation.message, session_id=session_id, result=result.to_dict())
            return result
        append_observation_audit(observation, "audit_decisions", resume_decision_audit(pending_task, plan=plan))

        final_message = "Resumed pending GIS task completed."
        result = completed_result(
            final_message,
            steps=steps,
            state_tree=self.state.to_dict(),
            session_id=session_id,
        )
        self.emit(on_event, "completed", final_message, session_id=session_id, result=result.to_dict())
        return result

    def _pause_resumed_plan(
        self,
        plan: ActionPlan,
        *,
        issues: list[ValidationIssue],
        pending_task: dict,
        original_request: str,
        session_id: str,
        on_event: EventHandler | None,
        event: str,
        prior_steps: list[ReActStep] | None = None,
    ) -> AgentResult:
        steps = list(prior_steps or [])
        primary_issue = issues[0]
        prompt_message = primary_issue.repair.message if primary_issue.repair else primary_issue.message
        risks = risks_from_issues(issues, tool_name=plan.action, state_tree=self.state)
        decision = RiskPolicy().evaluate(risks)
        primary_risk = decision.primary_risk
        status = "awaiting_confirmation" if decision.kind == "ask_confirmation" else "awaiting_user"
        if primary_issue.stage == "semantic":
            next_pending_task = self.pending_task_from_issue(
                plan,
                primary_issue,
                original_request=original_request,
                state_tree=self.state.to_dict(),
                risk=primary_risk,
            )
        else:
            missing_slots = _preflight_missing_slots(plan, primary_issue)
            choices = pending_choices_from_context(
                plan,
                primary_issue,
                missing_slots=missing_slots,
                risk=primary_risk,
                state_tree=self.state.to_dict(),
            )
            next_pending_task = PendingTask(
                active_intent=plan.action,
                source="missing_slot_validation" if status == "awaiting_user" and missing_slots else "",
                pending_kind="choice" if choices else "form",
                filled_slots={
                    key: value
                    for key, value in normalize_semantic_input(plan.action, plan.action_input).items()
                    if key not in missing_slots and value is not None and str(value).strip() != ""
                },
                missing_slots=missing_slots,
                original_request=original_request,
                last_question_key=primary_issue.repair.message_key if primary_issue.repair else primary_issue.message_key,
                last_question_params=dict(primary_issue.repair.params if primary_issue.repair else primary_issue.params),
                awaiting_state=status,
                allowed_actions=allowed_resume_actions(status),
                risk=primary_risk.to_dict() if primary_risk else {},
                risk_code=primary_risk.code if primary_risk else "",
                confirmation_type=primary_risk.category if primary_risk else "",
                choices=choices,
                question=prompt_message,
            )
        next_pending_task.correction_history = list(pending_task.get("correction_history") or []) + [
            {"resumed_action": plan.to_dict(), "issues": [issue.to_dict() for issue in issues]}
        ]
        result = awaiting_result(
            prompt_message,
            steps=steps,
            state_tree=self.state.to_dict(),
            session_id=session_id,
            status=status,
            issues=issues,
            risks=risks,
            pending_task=next_pending_task,
            repair=primary_issue.repair,
        )
        self.emit(
            on_event,
            event,
            prompt_message,
            session_id=session_id,
            action=plan.action,
            issues=[issue.to_dict() for issue in issues],
            risks=[risk.to_dict() for risk in risks],
            risk=primary_risk.to_dict() if primary_risk else {},
            risk_decision=decision.to_dict(),
            repair=primary_issue.repair.to_dict() if primary_issue.repair else {},
            pending_task=next_pending_task.to_dict(),
            result=result.to_dict(),
        )
        return result


def _preflight_missing_slots(plan: ActionPlan, issue: ValidationIssue) -> list[str]:
    if issue.code == "unknown_field":
        missing_fields = {str(item) for item in list(issue.params.get("fields") or [])}
        slots = [
            key
            for key, value in dict(plan.action_input or {}).items()
            if str(value) in missing_fields or (isinstance(value, list) and missing_fields.intersection(str(item) for item in value))
        ]
        return slots or ["field"]
    if issue.code == "unknown_layer":
        missing_layer = str(issue.params.get("layer") or "")
        slots = [
            key
            for key, value in dict(plan.action_input or {}).items()
            if str(value) == missing_layer and (key.endswith("_ref") or key.endswith("_refs") or key == "layer_ref")
        ]
        return slots or ["input_ref"]
    return list(issue.params.get("missing_slots") or [])
