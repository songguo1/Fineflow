"""Duplicate action handling for resumed ReAct runs."""

from __future__ import annotations

from dataclasses import dataclass

from pineflow_agent.core.models import ActionPlan, ReActStep
from pineflow_agent.core.state_tree import GISStateTree
from pineflow_agent.orchestration.event_stream import EventHandler, emit_event
from pineflow_agent.orchestration.execution.execution_memory import ExecutionMemory
from pineflow_agent.orchestration.execution.execution_step import record_observation_step


@dataclass(frozen=True)
class DuplicateActionGuard:
    memory: ExecutionMemory
    state: GISStateTree
    steps: list[ReActStep]
    session_id: str
    on_event: EventHandler | None
    step_total: int

    def handle(self, plan: ActionPlan, *, index: int) -> bool:
        if plan.action == "final_answer" or not self.memory.has_completed(plan):
            return False
        duplicate_observation = self.memory.duplicate_observation(plan)
        emit_event(
            self.on_event,
            "retry",
            duplicate_observation.message,
            session_id=self.session_id,
            step_index=index,
            step_total=self.step_total,
            action=plan.action,
            observation=duplicate_observation.to_dict(),
        )
        record_observation_step(
            plan,
            duplicate_observation,
            index=index,
            step_total=self.step_total,
            steps=self.steps,
            on_event=self.on_event,
            session_id=self.session_id,
            state=self.state,
        )
        return True
