"""Run setup helpers for the ReAct loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pineflow_agent.core.models import ReActStep
from pineflow_agent.orchestration.event_stream import EventHandler, emit_event
from pineflow_agent.orchestration.execution.execution_memory import ExecutionMemory
from pineflow_agent.orchestration.hooks.contexts import HookContext, HookPoint
from pineflow_agent.orchestration.session_memory import read_session_memory


@dataclass(frozen=True)
class RunState:
    steps: list[ReActStep]
    step_total: int
    memory: ExecutionMemory
    session_memory: str


@dataclass(frozen=True)
class RunLifecycle:
    hooks: Any
    toolbox: Any
    state_tree: dict[str, Any]

    def start(
        self,
        user_request: str,
        *,
        session_id: str,
        on_event: EventHandler | None,
        steps: list[ReActStep],
    ) -> RunState:
        memory = ExecutionMemory.from_steps(steps)
        if session_id and hasattr(self.toolbox, "set_session_id"):
            self.toolbox.set_session_id(session_id)
        session_memory = read_session_memory(self.toolbox, user_request=user_request) if session_id else ""

        before_ctx = HookContext(
            user_request=user_request,
            session_id=session_id,
            session_memory=session_memory,
            state_tree=self.state_tree,
            prior_steps=steps,
        )
        self.hooks.emit(HookPoint.BEFORE_RUN, before_ctx)

        emit_event(
            on_event,
            "observe",
            "Observed current GIS state.",
            session_id=session_id,
            state_tree=self.state_tree,
        )
        return RunState(
            steps=steps,
            step_total=0,
            memory=memory,
            session_memory=session_memory,
        )
