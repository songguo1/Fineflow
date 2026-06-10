"""Resume handling for proactive clarification pending tasks."""

from __future__ import annotations

from typing import Any, Callable

from pineflow_agent.core.models import ActionPlan, AgentResult, Observation, ReActStep
from pineflow_agent.core.state_tree import GISStateTree
from pineflow_agent.orchestration.agent.result_builder import awaiting_result
from pineflow_agent.orchestration.event_stream import EventHandler
from pineflow_agent.orchestration.hooks.pipeline import HookPipeline
from pineflow_agent.orchestration.resume.resume_decision import ResumeActionApplier, ResumeDecisionParser
from pineflow_agent.orchestration.resume.resumed_plan_executor import ResumedPlanExecutor
from pineflow_agent.rules.validation import PendingTask
from pineflow_agent.llm.llm import LLMClient
from pineflow_agent.tools.registry.tool_registry import ToolRegistry

Emit = Callable[..., None]
ExecuteStep = Callable[..., Observation]
PendingTaskFactory = Callable[..., PendingTask]


class ClarificationResumeHandler:
    """Converts structured clarification choices into normal slot patches."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        state: GISStateTree,
        emit: Emit,
        execute_action_step: ExecuteStep,
        pending_task_from_issue: PendingTaskFactory,
        tool_registry: ToolRegistry,
        hooks: HookPipeline,
    ) -> None:
        self.state = state
        self.emit = emit
        self.execute_action_step = execute_action_step
        self.pending_task_from_issue = pending_task_from_issue
        self.tool_registry = tool_registry
        self.hooks = hooks
        self.decision_parser = ResumeDecisionParser(llm)

    def resume_with_slot_patch(
        self,
        *,
        pending_task: dict[str, Any],
        slot_patch: dict[str, Any],
        session_id: str,
        on_event: EventHandler | None,
        prior_steps: list[dict[str, Any]] | list[ReActStep] | None = None,
    ) -> AgentResult:
        cleaned_patch, patch_error = self._validated_patch(pending_task, slot_patch)
        if patch_error:
            return self._awaiting_clarification(
                pending_task,
                session_id=session_id,
                on_event=on_event,
                extra_history={
                    "slot_patch": ResumeActionApplier.clean_slot_patch(slot_patch),
                    "decision": "ask_again",
                    "reason": patch_error,
                },
            )
        clarification_decision = self._clarification_decision(pending_task, cleaned_patch)
        self.emit(
            on_event,
            "resume",
            "Resuming clarification with a structured slot patch.",
            session_id=session_id,
            pending_task=pending_task,
            slot_patch=cleaned_patch,
            clarification_decision=clarification_decision,
        )
        plan = ResumeActionApplier.plan_from_slot_patch(
            thought="Resume after the user answered a proactive clarification.",
            pending_task=pending_task,
            slot_patch=cleaned_patch,
        )
        return self._execute(plan, pending_task=pending_task, session_id=session_id, on_event=on_event, prior_steps=prior_steps)

    def resume_with_user_reply(
        self,
        *,
        pending_task: dict[str, Any],
        user_reply: str,
        session_id: str,
        on_event: EventHandler | None,
        prior_steps: list[dict[str, Any]] | list[ReActStep] | None = None,
    ) -> AgentResult:
        patch = self._patch_from_choice_reply(pending_task, user_reply)
        if patch:
            return self.resume_with_slot_patch(
                pending_task=pending_task,
                slot_patch=patch,
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
        decision = self.decision_parser.parse(
            user_reply=user_reply,
            pending_task=pending_task,
            state=self.state.to_dict(),
        )
        if str(decision.get("decision") or "").strip() == "patch_slots":
            return self.resume_with_slot_patch(
                pending_task=pending_task,
                slot_patch=dict(decision.get("slot_patch") or {}),
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
        return self._awaiting_clarification(
            pending_task,
            session_id=session_id,
            on_event=on_event,
            extra_history={"user_reply": user_reply, "decision": "ask_again"},
        )

    def _execute(
        self,
        plan: ActionPlan,
        *,
        pending_task: dict[str, Any],
        session_id: str,
        on_event: EventHandler | None,
        prior_steps: list[dict[str, Any]] | list[ReActStep] | None,
    ) -> AgentResult:
        return ResumedPlanExecutor(
            state=self.state,
            emit=self.emit,
            execute_action_step=self.execute_action_step,
            pending_task_from_issue=self.pending_task_from_issue,
            tool_registry=self.tool_registry,
            hooks=self.hooks,
        ).validate_or_execute(
            plan,
            pending_task=pending_task,
            original_request=str(pending_task.get("original_request") or ""),
            session_id=session_id,
            on_event=on_event,
            prior_steps=prior_steps,
        )

    def _validated_patch(self, pending_task: dict[str, Any], slot_patch: dict[str, Any]) -> tuple[dict[str, Any], str]:
        patch = ResumeActionApplier.clean_slot_patch(slot_patch)
        schema = dict(pending_task.get("slot_patch_schema") or {})
        if not schema:
            return (patch, "") if patch else ({}, "No schema-ready clarification patch was supplied.")
        allowed = set(str(slot) for slot in schema.keys())
        filtered = {key: value for key, value in patch.items() if key in allowed}
        if not filtered:
            return {}, "No allowed clarification slots were supplied."
        required = {
            str(slot)
            for slot, item in schema.items()
            if isinstance(item, dict) and item.get("required") is True
        }
        missing_required = [slot for slot in sorted(required) if not self._schema_ready_value(filtered.get(slot), schema.get(slot))]
        if missing_required:
            return {}, f"Missing required clarification slots: {', '.join(missing_required)}."
        invalid_types = [
            slot
            for slot, item in schema.items()
            if slot in filtered and not self._schema_ready_value(filtered.get(slot), item)
        ]
        if invalid_types:
            return {}, f"Clarification slot values did not satisfy schema: {', '.join(invalid_types)}."
        return filtered, ""

    def _clarification_decision(self, pending_task: dict[str, Any], slot_patch: dict[str, Any]) -> dict[str, Any]:
        risk = dict(pending_task.get("risk") or {})
        diagnosis = dict(risk.get("diagnosis") or {})
        recommendation = diagnosis.get("crs_recommendation")
        source = str(pending_task.get("source") or "proactive_clarification")
        return {
            "decision": "missing_slot_answered" if source == "missing_slot_validation" else "proactive_clarification_answered",
            "source": source,
            "question": str(pending_task.get("question") or pending_task.get("last_question") or ""),
            "active_intent": str(pending_task.get("active_intent") or ""),
            "slot_patch": dict(slot_patch or {}),
            "selected_choices": self._selected_choices(pending_task, slot_patch),
            "risk": risk,
            "crs_recommendation": dict(recommendation) if isinstance(recommendation, dict) else {},
            "selected_crs": str(slot_patch.get("target_crs") or ""),
        }

    @staticmethod
    def _selected_choices(pending_task: dict[str, Any], slot_patch: dict[str, Any]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for choice in list(pending_task.get("choices") or []):
            if not isinstance(choice, dict):
                continue
            slot = str(choice.get("slot") or "").strip()
            if not slot or slot not in slot_patch:
                continue
            if choice.get("value") == slot_patch.get(slot):
                selected.append(dict(choice))
        return selected

    @staticmethod
    def _patch_from_choice_reply(pending_task: dict[str, Any], user_reply: str) -> dict[str, Any]:
        text = str(user_reply or "").strip()
        if not text:
            return {}
        choices = [choice for choice in list(pending_task.get("choices") or []) if isinstance(choice, dict)]
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(choices):
                choice = choices[index]
                slot = str(choice.get("slot") or "").strip()
                if slot and "value" in choice:
                    return {slot: choice.get("value")}
        normalized = text.casefold()
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            slot = str(choice.get("slot") or "").strip()
            if not slot or "value" not in choice:
                continue
            labels = {
                str(choice.get("label") or "").strip().casefold(),
                str(choice.get("value") or "").strip().casefold(),
                str(choice.get("layer_id") or "").strip().casefold(),
                str(choice.get("field") or "").strip().casefold(),
            }
            labels.discard("")
            if normalized in labels:
                return {slot: choice.get("value")}
        return {}

    @staticmethod
    def _schema_ready_value(value: Any, schema: Any) -> bool:
        if not isinstance(schema, dict) or not schema:
            return value is not None
        enum_values = [str(item) for item in list(schema.get("enum") or []) if str(item or "").strip()]
        if enum_values:
            return str(value or "").strip() in enum_values
        expected_type = str(schema.get("type") or "").strip()
        if expected_type == "array":
            return isinstance(value, list) and bool(value)
        if expected_type == "string":
            if isinstance(value, str):
                return value.strip() != ""
            return value is not None
        return value is not None

    def _awaiting_clarification(
        self,
        pending_task: dict[str, Any],
        *,
        session_id: str,
        on_event: EventHandler | None,
        extra_history: dict[str, Any],
    ) -> AgentResult:
        message = str(pending_task.get("question") or pending_task.get("last_question") or "请选择一个结构化选项后继续。")
        result = awaiting_result(
            message,
            steps=[],
            state_tree=self.state.to_dict(),
            session_id=session_id,
            pending_task=self._pending_task(pending_task, extra_history=extra_history),
        )
        self.emit(
            on_event,
            "question",
            message,
            session_id=session_id,
            pending_task=result.pending_task.to_dict() if result.pending_task else {},
            result=result.to_dict(),
        )
        return result

    @staticmethod
    def _pending_task(pending_task: dict[str, Any], *, extra_history: dict[str, Any]) -> PendingTask:
        payload = dict(pending_task or {})
        payload["awaiting_state"] = "awaiting_user"
        payload["allowed_actions"] = list(payload.get("allowed_actions") or ["patch", "cancel", "replan"])
        payload["correction_history"] = list(payload.get("correction_history") or []) + [extra_history]
        payload["question"] = str(payload.get("question") or payload.get("last_question") or "")
        payload["ux_explanation"] = str(payload.get("ux_explanation") or payload.get("question") or "")
        return PendingTask.from_payload(payload)
