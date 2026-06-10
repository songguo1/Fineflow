"""Run-scoped client control action contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pineflow_api.contracts.models import QGISAgentRequest, ResumePayload

RunControlActionType = Literal[
    "pending.answer",
    "pending.patch_slots",
    "pending.reject",
    "pending.cancel",
    "pending.replan",
    "run.pause",
    "run.cancel",
    "run.resume",
]

RUN_CONTROL_ACTIONS: set[str] = {
    "run.pause",
    "run.cancel",
}

PENDING_CONTROL_ACTIONS: set[str] = {
    "pending.answer",
    "pending.patch_slots",
    "pending.reject",
    "pending.cancel",
    "pending.replan",
    "run.resume",
}

RESUME_ACTION_TYPES: dict[str, str] = {
    "confirm": "pending.answer",
    "patch": "pending.patch_slots",
    "reject": "pending.reject",
    "cancel": "pending.cancel",
    "replan": "pending.replan",
}


class RunControlAction(BaseModel):
    action_type: RunControlActionType
    run_id: str = ""
    pending_id: str = ""
    message: str = ""
    slot_patch: dict[str, Any] = Field(default_factory=dict)
    decision: str = ""
    client_seq: int | None = None
    request: QGISAgentRequest | None = None

    def validate_run_id(self, path_run_id: str) -> str:
        route_run_id = str(path_run_id or "").strip()
        payload_run_id = str(self.run_id or "").strip()
        if not route_run_id:
            raise ValueError("run_id is required.")
        if payload_run_id and payload_run_id != route_run_id:
            raise ValueError("Control action run_id does not match request path.")
        return route_run_id

    def to_resume_request(self, *, run_id: str) -> QGISAgentRequest:
        self.validate_run_id(run_id)
        resume = ResumePayload(
            action=self._resume_action(),
            slot_patch=dict(self.slot_patch or {}),
            message=str(self.message or "resume").strip() or "resume",
        )
        base = self.request or QGISAgentRequest(message=resume.message)
        return base.model_copy(
            update={
                "message": str(self.message or base.message or "resume").strip() or "resume",
                "resume": resume,
            }
        )

    def _resume_action(self) -> str:
        action_type = str(self.action_type or "").strip()
        if action_type == "pending.patch_slots":
            return "patch"
        if action_type == "pending.reject":
            return "reject"
        if action_type == "pending.cancel":
            return "cancel"
        if action_type == "pending.replan":
            return "replan"
        if action_type in {"pending.answer", "run.resume"}:
            decision = str(self.decision or "confirm").strip()
            if decision in {"confirm", "reject", "patch", "cancel", "replan"}:
                return decision
            raise ValueError(f"Unsupported pending decision: {decision or '<empty>'}.")
        raise ValueError(f"Unsupported pending control action: {action_type or '<empty>'}.")


class RunControlResult(BaseModel):
    ok: bool = True
    action_type: str = ""
    run_id: str = ""
    session_id: str = ""
    run: dict[str, Any] = Field(default_factory=dict)
    next_run_id: str = ""


def control_action_from_resume_request(run_id: str, request: QGISAgentRequest) -> RunControlAction:
    resume = request.resume
    if resume is None:
        raise ValueError("Resume request is missing resume payload.")
    action = str(resume.action or "").strip()
    action_type = RESUME_ACTION_TYPES.get(action)
    if not action_type:
        raise ValueError(f"Unsupported resume action: {action or '<empty>'}.")
    return RunControlAction(
        action_type=action_type,  # type: ignore[arg-type]
        run_id=run_id,
        message=resume.message or request.message,
        slot_patch=dict(resume.slot_patch or {}),
        decision=action,
        request=request,
    )


def normalize_run_control_result(result: dict[str, Any], *, action_type: str, fallback_run_id: str) -> dict[str, Any]:
    payload = dict(result or {})
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    run_id = str(payload.get("run_id") or run.get("run_id") or fallback_run_id or "").strip()
    session_id = str(payload.get("session_id") or run.get("session_id") or "").strip()
    next_run_id = str(payload.get("next_run_id") or run_id or fallback_run_id or "").strip()
    payload.update(
        RunControlResult(
            ok=bool(payload.get("ok", True)),
            action_type=str(payload.get("action_type") or action_type or ""),
            run_id=run_id,
            session_id=session_id,
            run=run,
            next_run_id=next_run_id,
        ).model_dump()
    )
    return payload
