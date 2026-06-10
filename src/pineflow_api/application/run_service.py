"""Run lifecycle boundary for PineFlow execution attempts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pineflow_api.contracts.run_events import normalize_run_event
from pineflow_api.contracts.run_lifecycle import RunStatus
from pineflow_api.contracts.transcript_projection import ensure_transcript_item_identity
from pineflow_api.persistence.sessions import SessionStore

EventSink = Callable[[dict[str, Any]], None]
DecorateResult = Callable[..., dict[str, Any]]
AttachTranscriptItem = Callable[[dict[str, Any], dict[int, dict[str, Any]]], None]


@dataclass
class RunContext:
    session_id: str
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    step_contexts: dict[int, dict[str, Any]] = field(default_factory=dict)
    current_result: dict[str, Any] = field(default_factory=dict)
    request_payload: dict[str, Any] = field(default_factory=dict)
    initial_user_message: str = ""


class RunService:
    """Owns run lifecycle persistence and event emission for API turns."""

    def __init__(self, sessions: SessionStore) -> None:
        self.sessions = sessions

    def begin(self, session_id: str, *, route_kind: str = "", message: str = "") -> RunContext:
        run_id = self.sessions.begin_run(session_id, route_kind=route_kind, message=message)
        return RunContext(session_id=session_id, run_id=run_id)

    def emit(
        self,
        context: RunContext,
        event: dict[str, Any],
        *,
        on_event: EventSink | None = None,
        decorate_result: DecorateResult | None = None,
        attach_transcript_item: AttachTranscriptItem | None = None,
    ) -> dict[str, Any]:
        payload = normalize_run_event(dict(event), session_id=context.session_id, run_id=context.run_id)
        if attach_transcript_item is not None:
            attach_transcript_item(payload, context.step_contexts)
        if isinstance(payload.get("result"), dict) and decorate_result is not None:
            payload["result"] = decorate_result(
                context.session_id,
                dict(payload["result"]),
                event_count=len(context.events) + 1,
            )
        context.events.append(payload)
        stored_event = self.sessions.append_event(context.session_id, payload, run_id=context.run_id)
        payload["seq"] = stored_event.get("seq")
        payload["run_id"] = stored_event.get("run_id") or context.run_id
        if isinstance(payload.get("transcript_item"), dict):
            payload["transcript_item"]["session_id"] = context.session_id
            payload["transcript_item"]["run_id"] = payload["run_id"]
            if payload.get("seq"):
                payload["transcript_item"]["seq"] = payload["seq"]
            if stored_event.get("created_at"):
                payload["transcript_item"]["created_at"] = stored_event["created_at"]
            payload["transcript_item"] = ensure_transcript_item_identity(payload["transcript_item"])
        if on_event is not None:
            on_event(payload)
        return payload

    def finish(self, context: RunContext, *, status: str, error: str = "") -> None:
        self.sessions.finish_run(context.run_id, status=status, error=error)

    def mark_resumed(self, run_id: str) -> None:
        self.sessions.finish_run(run_id, status=RunStatus.RESUMED)

    def request_pause(self, run_id: str) -> dict[str, Any]:
        return self.sessions.request_run_status(run_id=run_id, status=RunStatus.PAUSE_REQUESTED)

    def request_cancel(self, run_id: str) -> dict[str, Any]:
        return self.sessions.request_run_status(run_id=run_id, status=RunStatus.CANCEL_REQUESTED)

    def get(self, run_id: str) -> dict[str, Any]:
        return self.sessions.get_run(run_id)

    def list_events(self, run_id: str, *, after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        return self.sessions.list_run_events(run_id, after_seq=after_seq, limit=limit)

    def should_pause_session(self, session_id: str) -> bool:
        latest = self.sessions.latest_run(session_id)
        return str(latest.get("status") or "") == RunStatus.PAUSE_REQUESTED

    def should_cancel_session(self, session_id: str) -> bool:
        latest = self.sessions.latest_run(session_id)
        return str(latest.get("status") or "") == RunStatus.CANCEL_REQUESTED
