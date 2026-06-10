"""Meta-tool execution branch for the ReAct loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pineflow_agent.core.models import ActionPlan, AgentResult, Observation, ReActStep
from pineflow_agent.orchestration.event_stream import EventHandler, emit_event
from pineflow_agent.orchestration.meta.meta_tool_dispatcher import MetaToolDispatcher
from pineflow_agent.orchestration.agent.result_builder import awaiting_result, failed_result
from pineflow_agent.tools.registry.tool_registry import ToolRegistry
from pineflow_agent.tools.registry.toolkits import ToolDisclosureController
from pineflow_agent.rules.validation import PendingTask

MetaActionStatus = Literal["continue", "terminal", "fallthrough"]


@dataclass(frozen=True)
class MetaActionDecision:
    status: MetaActionStatus
    result: AgentResult | None = None


@dataclass(frozen=True)
class MetaActionRuntime:
    meta: MetaToolDispatcher
    tool_disclosure: ToolDisclosureController
    tool_registry: ToolRegistry
    state_tree: dict
    steps: list[ReActStep]
    session_id: str
    on_event: EventHandler | None
    step_total: int
    execute_action_step: Callable[..., Observation]

    def handle(self, plan: ActionPlan, *, index: int) -> MetaActionDecision | None:
        if not self.meta.is_meta(plan.action):
            return None
        meta_def = self.meta.definition(plan.action)
        observation = self.execute_action_step(
            plan,
            index=index,
            step_total=self.step_total,
            steps=self.steps,
            on_event=self.on_event,
            session_id=self.session_id,
        )
        if observation.is_success:
            pending_task = _pending_task_from_meta_observation(observation)
            if pending_task is not None:
                result = awaiting_result(
                    observation.message,
                    steps=self.steps,
                    state_tree=self.state_tree,
                    session_id=self.session_id,
                    status="awaiting_user",
                    pending_task=pending_task,
                )
                emit_event(
                    self.on_event,
                    "question",
                    observation.message,
                    session_id=self.session_id,
                    step_index=index,
                    step_total=self.step_total,
                    action=plan.action,
                    action_input=plan.action_input,
                    pending_task=pending_task.to_dict(),
                    result=result.to_dict(),
                )
                return MetaActionDecision("terminal", result)
            emit_event(
                self.on_event,
                "toolkit_selection",
                observation.message,
                session_id=self.session_id,
                step_index=index,
                step_total=self.step_total,
                action=plan.action,
                action_input=plan.action_input,
                tool_disclosure=self.tool_disclosure.prompt_catalog(self.tool_registry),
                observation=observation.to_dict(),
            )
            if meta_def.continue_after_success:
                return MetaActionDecision("continue")
            return MetaActionDecision("fallthrough")

        if meta_def.fail_is_hard:
            result = failed_result(
                observation.message,
                steps=self.steps,
                state_tree=self.state_tree,
                session_id=self.session_id,
            )
            emit_event(
                self.on_event,
                "failed",
                result.final_message,
                session_id=self.session_id,
                result=result.to_dict(),
            )
            return MetaActionDecision("terminal", result)
        return MetaActionDecision("fallthrough")


def _pending_task_from_meta_observation(observation: Observation) -> PendingTask | None:
    data = dict(observation.data or {})
    if str(data.get("meta_status") or "") != "awaiting_user":
        return None
    payload = dict(data.get("pending_task") or {})
    if not payload:
        return None
    payload.setdefault("source", "proactive_clarification")
    payload.setdefault("awaiting_state", "awaiting_user")
    payload.setdefault("allowed_actions", ["patch", "cancel", "replan"])
    payload.setdefault("question", observation.message)
    payload.setdefault("ux_explanation", observation.message)
    return PendingTask.from_payload(payload)
