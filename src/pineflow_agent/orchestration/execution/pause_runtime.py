"""Run lifecycle pause/cancel handling for ReAct runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pineflow_agent.core.models import AgentResult, ReActStep
from pineflow_agent.orchestration.event_stream import EventHandler, emit_event
from pineflow_agent.orchestration.agent.result_builder import cancelled_result, paused_result


@dataclass(frozen=True)
class PauseRuntime:
    state_tree: dict[str, Any]
    steps: list[ReActStep]
    session_id: str
    on_event: EventHandler | None
    should_pause: Callable[[str], bool] | None = None
    should_cancel: Callable[[str], bool] | None = None

    def try_pause(self) -> AgentResult | None:
        if self.should_cancel is not None and self.should_cancel(self.session_id):
            return self._cancelled_result()
        if self.should_pause is not None and self.should_pause(self.session_id):
            return self._paused_result()
        return None

    def _paused_result(self) -> AgentResult:
        result = paused_result(self.steps, state_tree=self.state_tree, session_id=self.session_id)
        emit_event(
            self.on_event,
            "paused",
            "Paused by user.",
            session_id=self.session_id,
            result=result.to_dict(),
        )
        return result

    def _cancelled_result(self) -> AgentResult:
        result = cancelled_result(self.steps, state_tree=self.state_tree, session_id=self.session_id)
        emit_event(
            self.on_event,
            "cancelled",
            "Cancelled by user.",
            session_id=self.session_id,
            result=result.to_dict(),
        )
        return result
