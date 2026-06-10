"""Session detail/list read-model helpers for SessionStore."""

from __future__ import annotations

from datetime import UTC, datetime
import sqlite3
from typing import Any

from pineflow_agent.core.artifacts import ArtifactIndex
from pineflow_agent.core.file_state import workspace_file_state
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext
from pineflow_api.persistence.event_repository import EventRepository
from pineflow_api.persistence.run_repository import RunRepository
from pineflow_api.persistence.session_projector import SessionProjector, build_display_transcript
from pineflow_api.persistence.session_summary_repository import SessionSummaryRepository
from pineflow_api.persistence.snapshot_repository import SnapshotRepository


class SessionReadModel:
    def __init__(self, workspace: WorkspaceContext) -> None:
        self._workspace = workspace

    def load_session(self, conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
        bucket_state = SessionSummaryRepository.get_session_bucket_state(conn, session_id)
        if str(bucket_state.get("archived_at") or "") or str(bucket_state.get("deleted_at") or ""):
            return None
        events = EventRepository.list_session_events(conn, session_id)
        session_snapshot = SnapshotRepository.load_session_snapshot_payload(conn, session_id)
        if not session_snapshot and not events:
            return None
        if session_snapshot:
            session = dict(session_snapshot)
            session["events"] = events
        else:
            session = self._project_events(session_id, events)
        latest_run = RunRepository.latest_run_for_session(conn, session_id)
        latest_run_result = self._latest_run_result(conn, latest_run)
        hydrated = SessionProjector.hydrate_session_execution(
            session_id=session_id,
            session=session,
            events=events,
            latest_run_result=latest_run_result,
        )
        hydrated["display_transcript"] = build_display_transcript(
            session_transcript=dict(hydrated.get("transcript") or {}),
            active_run_transcript=dict(latest_run_result.get("transcript") or {}),
            active_run_id=str(latest_run.get("run_id") or ""),
        )
        return self.decorate_session(session_id, hydrated, latest_run=latest_run)

    def list_sessions(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in SessionSummaryRepository.list_active_sessions(conn):
            latest_run = RunRepository.latest_run_for_session(conn, str(row.get("session_id") or ""))
            status = str(latest_run.get("status") or row.get("status") or "unknown")
            items.append(
                {
                    "session_id": str(row.get("session_id") or ""),
                    "status": status,
                    "first_message": str(row.get("first_message") or ""),
                    "updated_at": str(row.get("updated_at") or ""),
                    "event_count": int(row.get("event_count") or 0),
                    "message_count": int(row.get("message_count") or 0),
                    "latest_run": latest_run,
                }
            )
        return items

    def merge_session_events(self, conn: sqlite3.Connection, session_id: str, session: dict[str, Any]) -> dict[str, Any]:
        incoming = [dict(item) for item in list(session.get("events") or []) if isinstance(item, dict)]
        existing = EventRepository.list_session_events(conn, session_id)
        payload = dict(session or {})
        payload["events"] = existing if len(existing) > len(incoming) else incoming
        return payload

    def decorate_session(
        self,
        session_id: str,
        session: dict[str, Any],
        *,
        latest_run: dict[str, Any],
        updated_at: str = "",
    ) -> dict[str, Any]:
        timestamp = str(updated_at or _utc_now())
        session_payload = make_json_safe(dict(session or {}))
        event_count = len(list(session_payload.get("events") or []))
        return SessionProjector.decorate_session(
            session_id=session_id,
            session=session_payload,
            latest_run=make_json_safe(dict(latest_run or {})),
            file_state=self.file_state(session_id, event_count=event_count, updated_at=timestamp),
            updated_at=timestamp,
        )

    def file_state(self, session_id: str, *, event_count: int, updated_at: str) -> dict[str, Any]:
        workspace = self._workspace.with_session(session_id)
        return workspace_file_state(
            workspace,
            artifacts=ArtifactIndex.for_workspace(workspace),
            event_count=event_count,
            updated_at=updated_at,
        )

    def _project_events(self, session_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        return SessionProjector.project_from_events(
            session_id,
            [dict(item) for item in list(events or []) if isinstance(item, dict)],
            SessionProjector.base_session(session_id),
        )

    @staticmethod
    def _latest_run_result(conn: sqlite3.Connection, latest_run: dict[str, Any]) -> dict[str, Any]:
        run_id = str(latest_run.get("run_id") or "").strip()
        if not run_id:
            return {}
        payload = SnapshotRepository.load_run_snapshot_payload(conn, run_id)
        if not payload:
            return {}
        return SessionProjector.latest_run_result_from_snapshot(dict(payload), latest_run)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
