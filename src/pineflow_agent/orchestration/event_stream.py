"""Event stream helpers for the GIS agent runtime."""

from __future__ import annotations

from typing import Any, Callable

from pineflow_agent.core.json_safety import make_json_safe

EventHandler = Callable[[dict[str, Any]], None]

EVENT_CONTRACTS: dict[str, tuple[str, str]] = {
    "session": ("run.session", "progress"),
    "observe": ("source.loaded", "workflow_step"),
    "thought": ("run.thought", "debug"),
    "summary": ("run.summary", "result"),
    "review": ("run.review", "debug"),
    "completed": ("run.completed", "result"),
    "failed": ("run.failed", "result"),
    "paused": ("run.paused", "progress"),
    "cancelled": ("run.cancelled", "result"),
    "step_start": ("workflow.step_started", "workflow_step"),
    "step_complete": ("workflow.step_completed", "workflow_step"),
    "action": ("tool.selected", "debug"),
    "command": ("tool.command", "debug"),
    "tool": ("tool.started", "progress"),
    "observation": ("tool.completed", "workflow_step"),
    "artifact": ("artifact.created", "result"),
    "stdout": ("tool.log", "debug"),
    "stderr": ("tool.error", "debug"),
    "warning": ("warning.emitted", "warning"),
    "empty_result": ("result.empty", "warning"),
    "repair": ("repair.started", "progress"),
    "confirmation": ("repair.confirmation_requested", "confirmation"),
    "question": ("user_input.requested", "question"),
    "before_export": ("export.before", "progress"),
    "repair_success": ("repair.completed", "progress"),
    "repair_failed": ("repair.failed", "progress"),
    "retry": ("repair.retry", "progress"),
    "toolkit_selection": ("toolkit.selected", "debug"),
}


def emit_event(
    on_event: EventHandler | None,
    event: str,
    message: str,
    **payload: Any,
) -> None:
    """Emit one JSON-safe event to the caller-provided stream handler."""
    if on_event is None:
        return
    event_payload = {"event": event, "message": message}
    event_payload.update(payload)
    on_event(enrich_event_contract(event_payload))


def enrich_event_contract(event: dict[str, Any]) -> dict[str, Any]:
    """Attach Event Contract v2 fields while preserving the legacy event name."""
    payload = make_json_safe(dict(event or {}))
    event_name = str(payload.get("event") or "").strip()
    event_type, display_kind = EVENT_CONTRACTS.get(event_name, (_fallback_event_type(event_name), "debug"))
    if event_name == "repair" and _repair_needs_confirmation(payload):
        display_kind = "confirmation"
        event_type = "repair.confirmation_requested"
    if event_name == "observation" and _observation_failed(payload):
        event_type = "tool.failed"
        display_kind = "workflow_step"
    if event_name == "failed" and isinstance(payload.get("repair_session"), dict):
        event_type = "repair.failed"
        display_kind = "progress"
    if not str(payload.get("event_type") or "").strip():
        payload["event_type"] = event_type
    if not str(payload.get("display_kind") or "").strip():
        payload["display_kind"] = display_kind
    return make_json_safe(payload)


def _fallback_event_type(event_name: str) -> str:
    if not event_name:
        return "event.unknown"
    return f"event.{event_name}"


def _repair_needs_confirmation(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("pending_task"), dict) and payload["pending_task"]:
        return True
    decision = payload.get("risk_decision")
    if not isinstance(decision, dict):
        return False
    return str(decision.get("kind") or decision.get("decision") or "").strip() in {
        "ask_user",
        "ask_confirmation",
        "ask_disambiguation",
    }


def _observation_failed(payload: dict[str, Any]) -> bool:
    observation = payload.get("observation")
    if not isinstance(observation, dict):
        return False
    return str(observation.get("status") or "").strip().lower() in {"error", "failed"}
