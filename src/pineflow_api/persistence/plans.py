"""SQLite persistence for PlanDraft records."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext
from pineflow_api.contracts.models import QGISAgentRequest
from pineflow_api.contracts.plans import PlanDraft


class PlanDraftStore:
    def __init__(self, *, root: str | Path | None = None, workspace: WorkspaceContext | None = None) -> None:
        self._lock = RLock()
        self._workspace = workspace or WorkspaceContext(root=root or ".")
        self._db_path = self._workspace.pineflow_dir / "pineflow_state.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def save(self, plan: PlanDraft, request: QGISAgentRequest | None) -> None:
        now = _utc_now()
        payload = make_json_safe(plan.model_dump())
        request_payload = make_json_safe(request.model_dump()) if request is not None else {}
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO plan_drafts(plan_id, session_id, status, payload_json, request_json, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(plan_id) DO UPDATE SET
                      session_id = excluded.session_id,
                      status = excluded.status,
                      payload_json = excluded.payload_json,
                      request_json = excluded.request_json,
                      updated_at = excluded.updated_at
                    """,
                    (
                        plan.plan_id,
                        plan.session_id,
                        plan.status,
                        json.dumps(payload, ensure_ascii=False),
                        json.dumps(request_payload, ensure_ascii=False),
                        now,
                    ),
                )
                conn.commit()

    def get(self, plan_id: str) -> tuple[PlanDraft, QGISAgentRequest | None] | None:
        plan_id = str(plan_id or "").strip()
        if not plan_id:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload_json, request_json FROM plan_drafts WHERE plan_id = ?",
                    (plan_id,),
                ).fetchone()
        if row is None:
            return None
        plan_payload = _loads_dict(row["payload_json"])
        request_payload = _loads_dict(row["request_json"])
        if not plan_payload:
            return None
        request = QGISAgentRequest.model_validate(request_payload) if request_payload else None
        return PlanDraft.model_validate(plan_payload), request

    def list(self, *, session_id: str = "", status: str = "active", limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = min(max(1, int(limit or 20)), 200)
        statuses = _statuses(status)
        params: list[Any] = []
        where = []
        if session_id:
            where.append("session_id = ?")
            params.append(str(session_id or ""))
        if statuses:
            where.append(f"status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        sql = "SELECT payload_json, updated_at FROM plan_drafts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()
        plans: list[dict[str, Any]] = []
        for row in rows:
            payload = _loads_dict(row["payload_json"])
            if not payload:
                continue
            payload["updated_at"] = str(row["updated_at"] or "")
            plans.append(make_json_safe(payload))
        return plans

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plan_drafts(
                  plan_id text primary key,
                  session_id text not null default '',
                  status text not null,
                  payload_json text not null,
                  request_json text not null,
                  updated_at text not null default ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_plan_drafts_session ON plan_drafts(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_plan_drafts_status ON plan_drafts(status)")
            conn.commit()


def _loads_dict(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _statuses(value: str) -> list[str]:
    status = str(value or "active").strip().lower()
    if status == "active":
        return ["draft", "approved"]
    if status == "all":
        return []
    if status in {"draft", "approved", "rejected", "executed"}:
        return [status]
    return ["draft", "approved"]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
