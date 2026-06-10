"""SQLite-backed session store with legacy split-file import support."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any
from uuid import uuid4

from pineflow_agent.core.artifacts import ArtifactIndex
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext
from pineflow_agent.core.workspace_state import WorkspaceStateStore
from pineflow_api.contracts.run_lifecycle import (
    COMPLETED_AT_STATUSES,
    RunStatus,
    can_mark_resumed,
    can_request_status,
    normalize_run_status,
)
from pineflow_api.contracts.run_events import normalize_run_event
from pineflow_api.contracts.run_snapshots import normalize_run_snapshot
from pineflow_api.persistence.event_repository import EventRepository
from pineflow_api.persistence.legacy_sessions import load_legacy_session
from pineflow_api.persistence.session_read_model import SessionReadModel
from pineflow_api.persistence.run_repository import RunRepository
from pineflow_api.persistence.session_projector import SessionProjector
from pineflow_api.persistence.session_summary_repository import SessionSummaryRepository
from pineflow_api.persistence.snapshot_repository import SnapshotRepository


_DB_INIT_LOCK = RLock()


class SessionStore:
    def __init__(self, *, root: str | Path | None = None, workspace: WorkspaceContext | None = None) -> None:
        self._lock = RLock()
        self._workspace = workspace or WorkspaceContext(root=root or ".")
        self._sessions_root = self._workspace.sessions_root_dir
        self._sessions_root.mkdir(parents=True, exist_ok=True)
        self._db_path = self._workspace.pineflow_dir / "pineflow_state.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._read_model = SessionReadModel(self._workspace)
        with _DB_INIT_LOCK:
            self._init_db()
            self._migrate_legacy_sessions_if_empty()

    @property
    def workspace(self) -> WorkspaceContext:
        return self._workspace

    def get(self, session_id: str) -> dict[str, Any] | None:
        session_id = str(session_id or "").strip()
        if not session_id:
            return None
        with self._lock:
            return self._load_session_from_sqlite(session_id)

    def append_event(self, session_id: str, event: dict[str, Any], *, run_id: str = "") -> dict[str, Any]:
        return self._append_event(session_id, event, run_id=run_id)

    def begin_run(self, session_id: str, *, route_kind: str = "", message: str = "") -> str:
        session_id = str(session_id or "").strip()
        if not session_id:
            raise ValueError("session_id is required.")
        run_id = uuid4().hex
        now = _utc_now()
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    SessionSummaryRepository.ensure_session_row(
                        conn,
                        session_id=session_id,
                        first_message=str(message or "")[:120],
                        updated_at=now,
                    )
                    RunRepository.insert_run(
                        conn,
                        run_id=run_id,
                        session_id=session_id,
                        status=RunStatus.RUNNING,
                        route_kind=str(route_kind or ""),
                        message=str(message or ""),
                        now=now,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        return run_id

    def finish_run(self, run_id: str, *, status: str, error: str = "") -> None:
        run_id = str(run_id or "").strip()
        if not run_id:
            return
        now = _utc_now()
        run_status = normalize_run_status(status, default=RunStatus.COMPLETED)
        with self._lock:
            with self._connect() as conn:
                current = RunRepository.get_run(conn, run_id)
                current_status = str(current.get("status") or "")
                if run_status == RunStatus.RESUMED and current_status and not can_mark_resumed(current_status):
                    return
                completed_at = now if run_status in COMPLETED_AT_STATUSES else ""
                RunRepository.update_finished_run(
                    conn,
                    run_id=run_id,
                    status=run_status,
                    error=str(error or ""),
                    updated_at=now,
                    completed_at=completed_at,
                )
                if current.get("session_id"):
                    self._sync_session_status_from_latest_run(conn, str(current.get("session_id") or ""))
                conn.commit()

    def list_runs(self, session_id: str) -> list[dict[str, Any]]:
        session_id = str(session_id or "").strip()
        if not session_id:
            return []
        with self._lock:
            with self._connect() as conn:
                return RunRepository.list_runs(conn, session_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_id = str(run_id or "").strip()
        if not run_id:
            return {}
        with self._lock:
            with self._connect() as conn:
                return RunRepository.get_run(conn, run_id)

    def save_run_snapshot(self, run_id: str, session_id: str, snapshot: dict[str, Any]) -> None:
        run_id = str(run_id or "").strip()
        session_id = str(session_id or "").strip()
        if not run_id or not session_id:
            return
        payload = normalize_run_snapshot(snapshot, run_id=run_id, session_id=session_id)
        now = _utc_now()
        payload["updated_at"] = str(payload.get("updated_at") or now)
        with self._lock:
            with self._connect() as conn:
                SnapshotRepository.upsert_run_snapshot(
                    conn,
                    run_id=run_id,
                    session_id=session_id,
                    payload=payload,
                    updated_at=now,
                )
                conn.commit()

    def get_run_snapshot(self, run_id: str) -> dict[str, Any]:
        run_id = str(run_id or "").strip()
        if not run_id:
            return {}
        with self._lock:
            with self._connect() as conn:
                payload = SnapshotRepository.load_run_snapshot_payload(conn, run_id)
                run = RunRepository.get_run(conn, run_id)
        if not payload:
            return {}
        return normalize_run_snapshot(
            payload,
            run_id=str(run.get("run_id") or payload.get("run_id") or ""),
            session_id=str(run.get("session_id") or payload.get("session_id") or ""),
            status=str(run.get("status") or payload.get("status") or ""),
            updated_at=str(run.get("updated_at") or payload.get("updated_at") or ""),
        )

    def list_events(self, session_id: str, *, after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        session_id = str(session_id or "").strip()
        if not session_id:
            return []
        safe_after = max(0, int(after_seq or 0))
        safe_limit = min(max(1, int(limit or 500)), 2000)
        with self._lock:
            with self._connect() as conn:
                return EventRepository.list_session_events(conn, session_id, after_seq=safe_after, limit=safe_limit)

    def list_run_events(self, run_id: str, *, after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        run_id = str(run_id or "").strip()
        if not run_id:
            return []
        safe_after = max(0, int(after_seq or 0))
        safe_limit = min(max(1, int(limit or 500)), 2000)
        with self._lock:
            with self._connect() as conn:
                return EventRepository.list_run_events(conn, run_id, after_seq=safe_after, limit=safe_limit)

    def latest_run(self, session_id: str) -> dict[str, Any]:
        session_id = str(session_id or "").strip()
        if not session_id:
            return {}
        with self._lock:
            with self._connect() as conn:
                return RunRepository.latest_run_for_session(conn, session_id)

    def request_run_status(self, *, session_id: str = "", run_id: str = "", status: str) -> dict[str, Any]:
        requested_status = normalize_run_status(status, default="")
        if not requested_status:
            raise ValueError("status is required.")
        with self._lock:
            with self._connect() as conn:
                target_run_id = str(run_id or "").strip()
                if not target_run_id:
                    latest = RunRepository.latest_run_for_session(conn, str(session_id or "").strip())
                    target_run_id = str(latest.get("run_id") or "")
                if not target_run_id:
                    return {}
                now = _utc_now()
                current = RunRepository.get_run(conn, target_run_id)
                if not current or not can_request_status(str(current.get("status") or ""), requested_status):
                    conn.commit()
                    return {}
                RunRepository.update_requested_status(conn, run_id=target_run_id, status=requested_status, updated_at=now)
                target_session_id = RunRepository.session_id_for_run(conn, target_run_id) or str(session_id or "").strip()
                if target_session_id:
                    self._sync_session_status_from_latest_run(conn, target_session_id)
                latest_run = RunRepository.latest_run_for_session(conn, target_session_id) if target_session_id else {}
                conn.commit()
        return latest_run

    def save(self, session: dict[str, Any], *, run_id: str = "") -> None:
        session_id = str(session.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required.")
        with self._lock:
            payload = self._merge_session_events(session_id, deepcopy(session))
            payload = self._decorate_session(session_id, payload)
            self._save_session_sqlite(session_id, payload, run_id=run_id)

    def _append_event(self, session_id: str, event: dict[str, Any], *, run_id: str = "") -> dict[str, Any]:
        session_id = str(session_id or "").strip()
        if not session_id:
            raise ValueError("session_id is required.")
        with self._lock:
            event_payload = normalize_run_event(dict(event or {}), session_id=session_id, run_id=run_id)
            session = self._load_session_from_sqlite(session_id) or SessionProjector.base_session(session_id)
            session.setdefault("events", []).append(event_payload)
            session = self._decorate_session(session_id, session)
            stored_event = self._append_event_sqlite(session_id, event_payload, session, run_id=run_id)
            return dict(stored_event)

    def artifact_outputs(self, session_id: str) -> list[dict[str, Any]]:
        session_id = str(session_id or "").strip()
        if not session_id:
            return []
        artifacts = ArtifactIndex.for_workspace(self._workspace.with_session(session_id))
        return artifacts.outputs()

    def get_report_artifact(self, session_id: str, artifact_id: str) -> dict[str, Any]:
        session_id = str(session_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        if not session_id or not artifact_id:
            return {}
        workspace = self._workspace.with_session(session_id)
        artifacts = ArtifactIndex.for_workspace(workspace)
        record = artifacts.find_record(artifact_id=artifact_id, role="report")
        if record is None:
            return {}
        report_path = Path(record.path)
        try:
            resolved_path = report_path.resolve()
            session_root = workspace.session_dir.resolve()
        except OSError:
            return {}
        if session_root not in resolved_path.parents:
            return {}
        if resolved_path.suffix.lower() != ".md" or not resolved_path.exists() or not resolved_path.is_file():
            return {}
        try:
            content = resolved_path.read_text(encoding="utf-8")
        except OSError:
            return {}
        payload = record.output_dict()
        payload["content"] = content
        return payload

    def file_state(self, session_id: str, *, event_count: int = 0, updated_at: str = "") -> dict[str, Any]:
        session_id = str(session_id or "").strip()
        if not session_id:
            return {}
        return self._read_model.file_state(
            session_id,
            event_count=event_count,
            updated_at=str(updated_at or _utc_now()),
        )

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [make_json_safe(dict(item)) for item in self._list_sessions_sqlite()]

    @staticmethod
    def _session_summary(session_id: str, session: dict[str, Any]) -> dict[str, Any]:
        return SessionProjector.session_summary(session_id, session)

    def archive_session(self, session_id: str) -> bool:
        return self._move_session_to_bucket(session_id, "archive")

    def delete_session(self, session_id: str) -> bool:
        return self._move_session_to_bucket(session_id, "trash")

    def _move_session_to_bucket(self, session_id: str, bucket: str) -> bool:
        session_id = str(session_id or "").strip()
        bucket = str(bucket or "").strip()
        if not session_id or not bucket or Path(session_id).name != session_id:
            return False
        if self.get(session_id) is None:
            return False
        now = _utc_now()
        with self._lock:
            with self._connect() as conn:
                SessionSummaryRepository.update_bucket(conn, session_id, bucket=bucket, updated_at=now)
                conn.commit()
        return True

    def get_session_memory(self, session_id: str) -> str:
        return self._state_store(session_id).read_memory()

    def save_session_memory(self, session_id: str, content: str) -> None:
        self._state_store(session_id).write_memory(content)

    def list_recent_outputs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return file paths from completed session final artifacts for reuse."""
        sessions = self.list_sessions()
        outputs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in list(sessions)[:limit]:
            sid = str(entry.get("session_id") or "")
            if not sid or str(entry.get("status") or "") != "completed":
                continue
            artifacts = ArtifactIndex.for_workspace(self._workspace.with_session(sid))
            for artifact in list(artifacts.outputs() or []):
                if not isinstance(artifact, dict):
                    continue
                if str(artifact.get("role") or "") != "final":
                    continue
                path = str(artifact.get("path") or "").strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                outputs.append({
                    "name": str(artifact.get("name") or ""),
                    "path": path,
                    "kind": str(artifact.get("kind") or ""),
                    "session_id": sid,
                })
        return outputs

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions(
                  session_id text primary key,
                  status text not null,
                  session_status text not null default 'active',
                  first_message text not null default '',
                  message_count integer not null default 0,
                  event_count integer not null default 0,
                  updated_at text not null,
                  archived_at text not null default '',
                  deleted_at text not null default ''
                );

                CREATE TABLE IF NOT EXISTS session_events(
                  id integer primary key autoincrement,
                  session_id text not null,
                  run_id text not null default '',
                  seq integer not null,
                  event_type text not null,
                  payload_json text not null,
                  created_at text not null,
                  unique(session_id, seq)
                );

                CREATE TABLE IF NOT EXISTS session_runs(
                  run_id text primary key,
                  session_id text not null,
                  status text not null,
                  route_kind text not null default '',
                  message text not null default '',
                  started_at text not null,
                  updated_at text not null,
                  completed_at text not null default '',
                  result_status text not null default '',
                  error text not null default ''
                );

                CREATE TABLE IF NOT EXISTS session_snapshots(
                  session_id text primary key,
                  payload_json text not null,
                  updated_at text not null
                );

                CREATE TABLE IF NOT EXISTS run_snapshots(
                  run_id text primary key,
                  session_id text not null,
                  payload_json text not null,
                  updated_at text not null
                );

                CREATE INDEX IF NOT EXISTS idx_session_events_session_seq
                  ON session_events(session_id, seq);
                CREATE INDEX IF NOT EXISTS idx_session_runs_session_started
                  ON session_runs(session_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                  ON sessions(updated_at);
                CREATE INDEX IF NOT EXISTS idx_run_snapshots_session
                  ON run_snapshots(session_id);
                """
            )
            self._ensure_column(conn, "session_events", "run_id", "text not null default ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_events_run ON session_events(run_id)")
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if any(str(row["name"] or "") == column for row in rows):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_legacy_sessions_if_empty(self) -> None:
        with self._connect() as conn:
            if SessionSummaryRepository.count_sessions(conn) > 0:
                return
        for entry in sorted(self._sessions_root.iterdir()) if self._sessions_root.exists() else []:
            if not entry.is_dir() or entry.name in {"archive", "trash"}:
                continue
            session_id = entry.name
            legacy = load_legacy_session(self._workspace.with_session(session_id))
            if not legacy:
                continue
            self._save_session_sqlite(session_id, legacy)

    def _load_session_from_sqlite(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            return self._read_model.load_session(conn, session_id)

    def _save_session_sqlite(self, session_id: str, session: dict[str, Any], *, run_id: str = "") -> None:
        payload = make_json_safe(dict(session or {}))
        events = [dict(item) for item in list(payload.get("events") or []) if isinstance(item, dict)]
        now = str(payload.get("updated_at") or _utc_now())
        payload["event_count"] = len(events)
        payload["updated_at"] = now
        snapshot_payload = self._session_snapshot_payload(payload, run_id=run_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._upsert_session_summary(conn, session_id, payload, updated_at=now, event_count=len(events))
                existing_event_count = EventRepository.count_session_events(conn, session_id)
                if existing_event_count != len(events):
                    EventRepository.replace_session_events(
                        conn,
                        session_id=session_id,
                        events=events,
                        run_id=run_id,
                        created_at=now,
                    )
                SnapshotRepository.upsert_session_snapshot(
                    conn,
                    session_id=session_id,
                    payload=snapshot_payload,
                    updated_at=now,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _append_event_sqlite(self, session_id: str, event: dict[str, Any], session: dict[str, Any], *, run_id: str = "") -> dict[str, Any]:
        now = _utc_now()
        payload = make_json_safe(dict(session or {}))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                seq = EventRepository.next_session_seq(conn, session_id)
                stored_event = normalize_run_event(
                    dict(event),
                    session_id=session_id,
                    run_id=run_id,
                    seq=seq,
                    created_at=now,
                )
                payload_events = [dict(item) for item in list(payload.get("events") or []) if isinstance(item, dict)]
                if payload_events:
                    payload_events[-1] = dict(stored_event)
                else:
                    payload_events = [dict(stored_event)]
                payload["events"] = payload_events
                payload = SessionProjector.apply_event_to_session(payload, stored_event)
                EventRepository.insert_event(
                    conn,
                    session_id=session_id,
                    run_id=str(run_id or ""),
                    seq=seq,
                    event_type=str(stored_event.get("event_type") or event.get("event") or ""),
                    payload=stored_event,
                    created_at=now,
                )
                self._upsert_session_summary(conn, session_id, payload, updated_at=now, event_count=seq)
                if isinstance(stored_event.get("result"), dict) or isinstance(stored_event.get("transcript_item"), dict):
                    payload["event_count"] = seq
                    payload["updated_at"] = now
                    snapshot_payload = self._session_snapshot_payload(payload, run_id=run_id)
                    SnapshotRepository.upsert_session_snapshot(
                        conn,
                        session_id=session_id,
                        payload=snapshot_payload,
                        updated_at=now,
                    )
                conn.commit()
                return stored_event
            except Exception:
                conn.rollback()
                raise

    def _list_sessions_sqlite(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._read_model.list_sessions(conn)

    def _sync_session_status_from_latest_run(self, conn: sqlite3.Connection, session_id: str) -> None:
        latest_run = RunRepository.latest_run_for_session(conn, session_id)
        latest_status = str(latest_run.get("status") or "").strip()
        if not latest_status:
            return
        SessionSummaryRepository.update_status(
            conn,
            session_id,
            status=latest_status,
            updated_at=str(latest_run.get("updated_at") or _utc_now()),
        )

    def _merge_session_events(self, session_id: str, session: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            return self._read_model.merge_session_events(conn, session_id, session)

    def _upsert_session_summary(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        session: dict[str, Any],
        *,
        updated_at: str,
        event_count: int,
    ) -> None:
        summary = self._session_summary(session_id, session)
        SessionSummaryRepository.upsert_summary(
            conn,
            session_id=session_id,
            status=str(summary.get("status") or "unknown"),
            session_status=str(session.get("session_status") or "active"),
            first_message=str(summary.get("first_message") or ""),
            message_count=int(summary.get("message_count") or 0),
            event_count=int(event_count),
            updated_at=updated_at,
        )

    def _state_store(self, session_id: str) -> WorkspaceStateStore:
        return WorkspaceStateStore(self._workspace.with_session(session_id or "session"))

    def _decorate_session(
        self,
        session_id: str,
        session: dict[str, Any],
        *,
        latest_run: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._read_model.decorate_session(
            session_id,
            session,
            latest_run=make_json_safe(dict(latest_run or self.latest_run(session_id))),
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    @staticmethod
    def _session_snapshot_payload(session: dict[str, Any], *, run_id: str = "") -> dict[str, Any]:
        return SessionProjector.session_snapshot_payload(session, run_id=run_id)

def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


SESSION_STORE = SessionStore()
