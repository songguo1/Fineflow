"""Resume event emission helpers."""

from __future__ import annotations

from typing import Any, Callable

from pineflow_agent.core.models import AgentResult
from pineflow_agent.orchestration.event_stream import EventHandler

Emit = Callable[..., None]


class ResumeEventEmitter:
    """Small wrapper around legacy resume event names and v2 enrichment."""

    def __init__(self, emit: Emit, on_event: EventHandler | None, *, session_id: str) -> None:
        self.emit = emit
        self.on_event = on_event
        self.session_id = session_id

    def resume(self, message: str, **payload: Any) -> None:
        self.emit(self.on_event, "resume", message, session_id=self.session_id, **payload)

    def failed(self, message: str, *, result: AgentResult) -> None:
        self.emit(self.on_event, "failed", message, session_id=self.session_id, result=result.to_dict())

    def completed(self, message: str, *, result: AgentResult) -> None:
        self.emit(self.on_event, "completed", message, session_id=self.session_id, result=result.to_dict())

    def question(self, message: str, *, pending_task: dict[str, Any], result: AgentResult) -> None:
        self.emit(
            self.on_event,
            "question",
            message,
            session_id=self.session_id,
            pending_task=pending_task,
            result=result.to_dict(),
        )

    def repair_success(
        self,
        message: str,
        *,
        step_index: int,
        step_total: int,
        action: str,
        repair_audit: dict[str, Any],
    ) -> None:
        self.emit(
            self.on_event,
            "repair_success",
            message,
            session_id=self.session_id,
            step_index=step_index,
            step_total=step_total,
            action=action,
            repair_audit=repair_audit,
        )
