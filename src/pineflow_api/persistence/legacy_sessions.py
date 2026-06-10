"""Legacy split-file session import helpers.

This module is only for one-time migration / fallback reads from pre-SQLite
session directories. New live session state should come from SQLite-backed
run/session snapshots and append-only events.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from pineflow_agent.core.artifacts import ArtifactIndex
from pineflow_agent.core.file_state import workspace_file_state
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext
from pineflow_agent.core.workspace_state import WorkspaceStateStore
from pineflow_api.persistence.session_projector import SessionProjector


def load_legacy_session(workspace: WorkspaceContext) -> dict[str, Any] | None:
    """Load one legacy session directory for one-time SQLite migration."""
    saved = WorkspaceStateStore(workspace).load()
    projected = _project_session_from_event_log(workspace, snapshot=saved)
    if projected is not None:
        return projected
    return saved


def _project_session_from_event_log(
    workspace: WorkspaceContext,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    # Replay is kept only for old events.jsonl sessions during migration.
    events = _read_event_log(workspace.session_dir / "events.jsonl")
    if not events:
        return None
    session = _session_projection_base(workspace, snapshot=snapshot)
    for event in events:
        session = SessionProjector.apply_event_to_session(session, event)
    session["events"] = events
    return _decorate_session(workspace, session)


def _session_projection_base(workspace: WorkspaceContext, *, snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if snapshot is None:
        return _empty_session(workspace)
    base = SessionProjector.copy_execution_fields(snapshot, session_id=workspace.session_id)
    return _decorate_session(workspace, base)


def _read_event_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    value = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(make_json_safe(dict(value)))
    except OSError:
        return []
    return events

def _decorate_session(workspace: WorkspaceContext, session: dict[str, Any]) -> dict[str, Any]:
    payload = make_json_safe(dict(session))
    payload["session_id"] = workspace.session_id
    payload.setdefault("session_status", "active")
    payload.setdefault("status", "running")
    payload.setdefault("last_run_status", str(payload.get("status") or ""))
    if not isinstance(payload.get("messages"), list):
        payload["messages"] = []
    if not isinstance(payload.get("request"), dict):
        payload["request"] = {}
    if not isinstance(payload.get("events"), list):
        payload["events"] = []
    updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    event_count = len(list(payload.get("events") or []))
    payload["file_state"] = workspace_file_state(
        workspace,
        artifacts=ArtifactIndex.for_workspace(workspace),
        event_count=event_count,
        updated_at=updated_at,
    )
    payload["state_version"] = 2
    payload["updated_at"] = updated_at
    payload["event_count"] = event_count
    return payload


def _empty_session(workspace: WorkspaceContext) -> dict[str, Any]:
    return _decorate_session(
        workspace,
        SessionProjector.base_session(workspace.session_id),
    )
