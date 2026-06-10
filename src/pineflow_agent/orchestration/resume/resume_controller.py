"""Structured resume controller for paused GIS tasks."""

from __future__ import annotations

from typing import Any, Callable

from pineflow_agent.orchestration.event_stream import EventHandler
from pineflow_agent.orchestration.hooks.pipeline import HookPipeline
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.llm.llm import LLMClient
from pineflow_agent.core.models import ActionPlan, AgentResult, Observation, ReActStep, react_steps_from_payload
from pineflow_agent.orchestration.agent.result_finalizer import BoundResultFinalizer, ResultFinalizer
from pineflow_agent.orchestration.agent.ux_narrator import UXNarrator
from pineflow_agent.orchestration.agent.result_builder import awaiting_result, failed_result
from pineflow_agent.orchestration.resume.clarification_resume_handler import ClarificationResumeHandler
from pineflow_agent.orchestration.resume.repair_resume_handler import RepairResumeHandler
from pineflow_agent.orchestration.resume.resume_decision import ResumeActionApplier, ResumeDecisionParser
from pineflow_agent.orchestration.resume.resumed_plan_executor import ResumedPlanExecutor
from pineflow_agent.rules.rules_gateway import RulesGateway
from pineflow_agent.core.state_tree import GISStateTree
from pineflow_agent.tools.qgis.toolbox import QGISToolbox
from pineflow_agent.tools.registry.tool_registry import ToolRegistry
from pineflow_agent.rules.validation import PendingTask, allowed_resume_actions

Emit = Callable[..., None]
ExecuteStep = Callable[..., Observation]
RunRequest = Callable[..., AgentResult]
PendingTaskFactory = Callable[..., PendingTask]


class ResumeController:
    """Handles explicit confirm/reject/patch/cancel/replan resume actions."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        toolbox: QGISToolbox,
        state: GISStateTree,
        emit: Emit,
        execute_action_step: ExecuteStep,
        run_request: RunRequest,
        pending_task_from_issue: PendingTaskFactory,
        rules_gateway: RulesGateway,
        tool_registry: ToolRegistry,
        hooks: HookPipeline,
    ) -> None:
        self.llm = llm
        self.toolbox = toolbox
        self.state = state
        self.emit = emit
        self.execute_action_step = execute_action_step
        self.run_request = run_request
        self.pending_task_from_issue = pending_task_from_issue
        self.rules_gateway = rules_gateway
        self.tool_registry = tool_registry
        self.hooks = hooks
        self.decision_parser = ResumeDecisionParser(llm)

    def resume_pending_task(
        self,
        *,
        action: str,
        pending_task: dict,
        repair: dict | None = None,
        slot_patch: dict | None = None,
        user_reply: str = "",
        user_request: str = "",
        session_id: str = "",
        on_event: EventHandler | None = None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
    ) -> AgentResult:
        normalized_action = str(action or "").strip()
        if normalized_action == "confirm":
            return self.run_confirmed_repair(
                pending_task=pending_task,
                repair=repair or {},
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
        if normalized_action == "patch":
            return self.resume_with_slot_patch(
                pending_task=pending_task,
                slot_patch=slot_patch or {},
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
        if normalized_action == "reject":
            return self.reject_pending_repair(
                pending_task=pending_task,
                repair=repair or {},
                session_id=session_id,
                on_event=on_event,
            )
        if normalized_action == "cancel":
            return self.cancel_pending_task(
                pending_task=pending_task,
                session_id=session_id,
                on_event=on_event,
            )
        if normalized_action == "replan":
            return self.resume_with_replanned_request(
                user_request=user_request or user_reply,
                pending_task=pending_task,
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
        if normalized_action in {"reply", "answer"}:
            return self.resume_with_user_reply(
                user_reply=user_reply,
                pending_task=pending_task,
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
        raise ValueError(f"Unsupported pending resume action: {normalized_action or '<empty>'}.")

    def run_confirmed_repair(
        self,
        *,
        pending_task: dict,
        repair: dict,
        session_id: str = "",
        on_event: EventHandler | None = None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
    ) -> AgentResult:
        runtime_events: list[dict[str, Any]] = []
        on_event = _capturing_event_sink(on_event, runtime_events)
        self._set_session(session_id)
        result = RepairResumeHandler(
            state=self.state,
            emit=self.emit,
            execute_action_step=self.execute_action_step,
            run_request=self.run_request,
            key_event_message=self._key_event_message,
        ).run_confirmed_repair(
            pending_task=pending_task,
            repair=repair,
            session_id=session_id,
            on_event=on_event,
            prior_steps=prior_steps,
        )
        return self._finalize_result(
            result,
            user_request=str(pending_task.get("original_request") or "").strip(),
            session_id=session_id,
            runtime_events=runtime_events,
        )

    def resume_with_slot_patch(
        self,
        *,
        pending_task: dict,
        slot_patch: dict,
        session_id: str = "",
        on_event: EventHandler | None = None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
    ) -> AgentResult:
        runtime_events: list[dict[str, Any]] = []
        on_event = _capturing_event_sink(on_event, runtime_events)
        self._set_session(session_id)

        if _is_clarification_pending(pending_task):
            result = self._clarification_handler().resume_with_slot_patch(
                pending_task=pending_task,
                slot_patch=slot_patch,
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
            return self._finalize_result(
                result,
                user_request=str(pending_task.get("original_request") or "").strip(),
                session_id=session_id,
                runtime_events=runtime_events,
            )

        cleaned_patch = ResumeActionApplier.clean_slot_patch(slot_patch)
        self.emit(
            on_event,
            "resume",
            "Resuming paused GIS task with an explicit slot patch.",
            session_id=session_id,
            pending_task=pending_task,
            slot_patch=cleaned_patch,
        )
        plan = ResumeActionApplier.plan_from_slot_patch(
            thought="Resume the pending GIS action with the explicit slot patch from the user.",
            pending_task=pending_task,
            slot_patch=cleaned_patch,
        )
        result = self._validate_or_execute_resumed_plan(
            plan,
            pending_task=pending_task,
            original_request=str(pending_task.get("original_request") or ""),
            session_id=session_id,
            on_event=on_event,
            prior_steps=prior_steps,
        )
        return self._finalize_result(
            result,
            user_request=str(pending_task.get("original_request") or "").strip(),
            session_id=session_id,
            runtime_events=runtime_events,
        )

    def resume_with_replanned_request(
        self,
        *,
        user_request: str,
        pending_task: dict,
        session_id: str = "",
        on_event: EventHandler | None = None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
    ) -> AgentResult:
        runtime_events: list[dict[str, Any]] = []
        on_event = _capturing_event_sink(on_event, runtime_events)
        self._set_session(session_id)
        del prior_steps

        request_text = str(user_request or "").strip()
        self.emit(
            on_event,
            "resume",
            "Resuming with a replanned GIS request.",
            session_id=session_id,
            pending_task=pending_task,
            user_reply=request_text,
        )
        if not request_text:
            message = "Please restate the new GIS task in one complete sentence."
            result = awaiting_result(
                message,
                steps=[],
                state_tree=self.state.to_dict(),
                session_id=session_id,
                pending_task=PendingTask(
                    active_intent=str(pending_task.get("active_intent") or ""),
                    filled_slots=dict(pending_task.get("filled_slots") or {}),
                    missing_slots=list(pending_task.get("missing_slots") or []),
                    original_request=str(pending_task.get("original_request") or ""),
                    last_question_key=message,
                    last_question_params={},
                    awaiting_state="awaiting_user",
                    allowed_actions=allowed_resume_actions("awaiting_user"),
                    correction_history=list(pending_task.get("correction_history") or []),
                ),
            )
            self.emit(
                on_event,
                "question",
                message,
                session_id=session_id,
                pending_task=result.pending_task.to_dict() if result.pending_task else {},
                result=result.to_dict(),
            )
            return self._finalize_result(
                result,
                user_request=str(pending_task.get("original_request") or request_text).strip(),
                session_id=session_id,
                runtime_events=runtime_events,
            )
        result = self.run_request(request_text, session_id=session_id, on_event=on_event)
        return self._finalize_result(
            result,
            user_request=request_text,
            session_id=session_id,
            runtime_events=runtime_events,
        )

    def reject_pending_repair(
        self,
        *,
        pending_task: dict,
        repair: dict | None = None,
        session_id: str = "",
        on_event: EventHandler | None = None,
    ) -> AgentResult:
        runtime_events: list[dict[str, Any]] = []
        on_event = _capturing_event_sink(on_event, runtime_events)
        self._set_session(session_id)

        message_key = "repair.rejected"
        self.emit(
            on_event,
            "resume",
            "The user rejected the suggested GIS repair.",
            session_id=session_id,
            pending_task=pending_task,
            repair=repair or {},
        )
        next_pending_task = PendingTask(
            active_intent=str(pending_task.get("active_intent") or ""),
            filled_slots=dict(pending_task.get("filled_slots") or {}),
            missing_slots=list(pending_task.get("missing_slots") or []),
            original_request=str(pending_task.get("original_request") or ""),
            last_question_key=message_key,
            last_question_params={},
            awaiting_state="awaiting_user",
            allowed_actions=["cancel", "replan"],
            correction_history=list(pending_task.get("correction_history") or [])
            + [{"rejected_repair": make_json_safe(repair or {})}],
        )
        message = next_pending_task.last_question
        result = awaiting_result(
            message,
            steps=[],
            state_tree=self.state.to_dict(),
            session_id=session_id,
            pending_task=next_pending_task,
        )
        self.emit(
            on_event,
            "question",
            message,
            session_id=session_id,
            pending_task=next_pending_task.to_dict(),
            result=result.to_dict(),
        )
        return self._finalize_result(
            result,
            user_request=str(pending_task.get("original_request") or "").strip(),
            session_id=session_id,
            runtime_events=runtime_events,
        )

    def cancel_pending_task(
        self,
        *,
        pending_task: dict,
        session_id: str = "",
        on_event: EventHandler | None = None,
    ) -> AgentResult:
        runtime_events: list[dict[str, Any]] = []
        on_event = _capturing_event_sink(on_event, runtime_events)
        self._set_session(session_id)

        final_message = "Cancelled the pending GIS task."
        self.emit(
            on_event,
            "resume",
            "The user cancelled the pending GIS task.",
            session_id=session_id,
            pending_task=pending_task,
        )
        result = failed_result(
            final_message,
            steps=[],
            state_tree=self.state.to_dict(),
            session_id=session_id,
            status="cancelled",
        )
        self.emit(on_event, "completed", final_message, session_id=session_id, result=result.to_dict())
        return self._finalize_result(
            result,
            user_request=str(pending_task.get("original_request") or "").strip(),
            session_id=session_id,
            runtime_events=runtime_events,
        )

    def resume_with_user_reply(
        self,
        *,
        user_reply: str,
        pending_task: dict,
        session_id: str = "",
        on_event: EventHandler | None = None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
    ) -> AgentResult:
        runtime_events: list[dict[str, Any]] = []
        on_event = _capturing_event_sink(on_event, runtime_events)
        self._set_session(session_id)

        if _is_clarification_pending(pending_task):
            result = self._clarification_handler().resume_with_user_reply(
                pending_task=pending_task,
                user_reply=user_reply,
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
            return self._finalize_result(
                result,
                user_request=str(pending_task.get("original_request") or user_reply).strip(),
                session_id=session_id,
                runtime_events=runtime_events,
            )

        self.emit(
            on_event,
            "resume",
            "Resuming paused GIS task from the user reply.",
            session_id=session_id,
            pending_task=pending_task,
            user_reply=user_reply,
        )

        decision = self.decision_parser.parse(
            user_reply=user_reply,
            pending_task=pending_task,
            state=self.state.to_dict(),
        )
        mode = str(decision.get("decision") or "").strip()
        self.emit(
            on_event,
            "thought",
            f"Resume decision: {mode or 'ask_again'}.",
            session_id=session_id,
            decision=decision,
        )
        if mode == "patch_slots":
            plan = ResumeActionApplier.plan_from_slot_patch(
                thought=str(decision.get("reason") or "Resume the pending GIS action with the supplied parameters."),
                pending_task=pending_task,
                slot_patch=dict(decision.get("slot_patch") or {}),
            )
            result = self._validate_or_execute_resumed_plan(
                plan,
                pending_task=pending_task,
                original_request=str(pending_task.get("original_request") or user_reply),
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
            return self._finalize_result(
                result,
                user_request=str(pending_task.get("original_request") or user_reply).strip(),
                session_id=session_id,
                runtime_events=runtime_events,
            )

        if mode == "replan":
            plan = ResumeActionApplier.plan_from_replan(decision)
            result = self._validate_or_execute_resumed_plan(
                plan,
                pending_task=pending_task,
                original_request=user_reply,
                session_id=session_id,
                on_event=on_event,
                prior_steps=prior_steps,
            )
            return self._finalize_result(
                result,
                user_request=user_reply,
                session_id=session_id,
                runtime_events=runtime_events,
            )

        message = str(
            decision.get("message")
            or pending_task.get("last_question")
            or "Please clarify the missing parameter."
        )
        result = awaiting_result(
            message,
            steps=[],
            state_tree=self.state.to_dict(),
            session_id=session_id,
            pending_task=PendingTask(
                active_intent=str(pending_task.get("active_intent") or ""),
                filled_slots=dict(pending_task.get("filled_slots") or {}),
                missing_slots=list(pending_task.get("missing_slots") or []),
                original_request=str(pending_task.get("original_request") or ""),
                last_question_key=str(pending_task.get("last_question_key") or ""),
                last_question_params=dict(pending_task.get("last_question_params") or {}),
                awaiting_state="awaiting_user",
                allowed_actions=allowed_resume_actions("awaiting_user"),
                correction_history=list(pending_task.get("correction_history") or [])
                + [{"user_reply": user_reply, "decision": make_json_safe(decision)}],
            ),
        )
        self.emit(
            on_event,
            "question",
            message,
            session_id=session_id,
            pending_task=result.pending_task.to_dict() if result.pending_task else {},
            result=result.to_dict(),
        )
        return self._finalize_result(
            result,
            user_request=str(pending_task.get("original_request") or "").strip(),
            session_id=session_id,
            runtime_events=runtime_events,
        )

    def _validate_or_execute_resumed_plan(
        self,
        plan: ActionPlan,
        *,
        pending_task: dict,
        original_request: str,
        session_id: str,
        on_event: EventHandler | None,
        prior_steps: list[dict] | list[ReActStep] | None = None,
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
            original_request=original_request,
            session_id=session_id,
            on_event=on_event,
            prior_steps=prior_steps,
        )

    def _set_session(self, session_id: str) -> None:
        if session_id and hasattr(self.toolbox, "set_session_id"):
            self.toolbox.set_session_id(session_id)

    def _finalize_result(
        self,
        result: AgentResult,
        *,
        user_request: str,
        session_id: str,
        runtime_events: list[dict[str, Any]],
    ) -> AgentResult:
        if not isinstance(result, AgentResult):
            return result
        if result.report_audit:
            return result
        finalizer = BoundResultFinalizer(
            finalizer=ResultFinalizer(hooks=self.hooks, toolbox=self.toolbox),
            user_request=str(user_request or "").strip(),
            steps=list(result.steps or []),
            session_id=session_id,
            session_memory_before="",
            runtime_events=list(runtime_events or []),
        )
        return finalizer(result)

    def _clarification_handler(self) -> ClarificationResumeHandler:
        return ClarificationResumeHandler(
            llm=self.llm,
            state=self.state,
            emit=self.emit,
            execute_action_step=self.execute_action_step,
            pending_task_from_issue=self.pending_task_from_issue,
            tool_registry=self.tool_registry,
            hooks=self.hooks,
        )

    def _key_event_message(self, event: str, payload: dict[str, Any], *, fallback: str) -> str:
        try:
            text = UXNarrator(self.llm).narrate_key_event(event, payload)
        except Exception:
            return fallback
        return str(text or "").strip() or fallback


def _is_clarification_pending(pending_task: dict[str, Any]) -> bool:
    return str(pending_task.get("source") or "").strip() in {"proactive_clarification", "missing_slot_validation"}


def _capturing_event_sink(
    on_event: EventHandler | None,
    runtime_events: list[dict[str, Any]],
) -> EventHandler:
    def capture(event: dict[str, Any]) -> None:
        if isinstance(event, dict):
            runtime_events.append(dict(event))
        if on_event is not None:
            on_event(event)

    return capture


