"""Shared run lifecycle contract for PineFlow execution attempts."""

from __future__ import annotations

from typing import Final


class RunStatus:
    CREATED: Final = "created"
    INITIALIZING: Final = "initializing"
    RUNNING: Final = "running"
    PAUSE_REQUESTED: Final = "pause_requested"
    PAUSED: Final = "paused"
    CANCEL_REQUESTED: Final = "cancel_requested"
    CANCELLED: Final = "cancelled"
    AWAITING_USER: Final = "awaiting_user"
    AWAITING_CONFIRMATION: Final = "awaiting_confirmation"
    COMPLETED: Final = "completed"
    FAILED: Final = "failed"
    RESUMED: Final = "resumed"


ALL_RUN_STATUSES: Final = {
    RunStatus.CREATED,
    RunStatus.INITIALIZING,
    RunStatus.RUNNING,
    RunStatus.PAUSE_REQUESTED,
    RunStatus.PAUSED,
    RunStatus.CANCEL_REQUESTED,
    RunStatus.CANCELLED,
    RunStatus.AWAITING_USER,
    RunStatus.AWAITING_CONFIRMATION,
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.RESUMED,
}

ACTIVE_RUN_STATUSES: Final = {
    RunStatus.CREATED,
    RunStatus.INITIALIZING,
    RunStatus.RUNNING,
    RunStatus.PAUSE_REQUESTED,
    RunStatus.CANCEL_REQUESTED,
}

PAUSABLE_RUN_STATUSES: Final = {
    RunStatus.CREATED,
    RunStatus.INITIALIZING,
    RunStatus.RUNNING,
    RunStatus.PAUSE_REQUESTED,
}

CANCELLABLE_RUN_STATUSES: Final = {
    RunStatus.CREATED,
    RunStatus.INITIALIZING,
    RunStatus.RUNNING,
    RunStatus.PAUSE_REQUESTED,
    RunStatus.CANCEL_REQUESTED,
    RunStatus.AWAITING_USER,
    RunStatus.AWAITING_CONFIRMATION,
}

COMPLETED_AT_STATUSES: Final = {
    RunStatus.PAUSED,
    RunStatus.CANCELLED,
    RunStatus.AWAITING_USER,
    RunStatus.AWAITING_CONFIRMATION,
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.RESUMED,
}

RESUMABLE_RUN_STATUSES: Final = {
    RunStatus.PAUSED,
    RunStatus.AWAITING_USER,
    RunStatus.AWAITING_CONFIRMATION,
}

REQUEST_STATUS_ALLOWED_FROM: Final = {
    RunStatus.PAUSE_REQUESTED: PAUSABLE_RUN_STATUSES,
    RunStatus.CANCEL_REQUESTED: CANCELLABLE_RUN_STATUSES,
}


def normalize_run_status(status: str, *, default: str = RunStatus.COMPLETED) -> str:
    normalized = str(status or "").strip()
    if normalized in ALL_RUN_STATUSES:
        return normalized
    return default


def can_request_status(current_status: str, requested_status: str) -> bool:
    requested = normalize_run_status(requested_status, default="")
    if not requested:
        return False
    return normalize_run_status(current_status, default="") in REQUEST_STATUS_ALLOWED_FROM.get(requested, set())


def can_mark_resumed(current_status: str) -> bool:
    return normalize_run_status(current_status, default="") in RESUMABLE_RUN_STATUSES
