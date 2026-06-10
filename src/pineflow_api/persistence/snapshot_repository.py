"""Snapshot SQL helpers for SessionStore."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class SnapshotRepository:
    @staticmethod
    def upsert_run_snapshot(
        conn: sqlite3.Connection,
        *,
        run_id: str,
        session_id: str,
        payload: dict[str, Any],
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO run_snapshots(run_id, session_id, payload_json, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              session_id = excluded.session_id,
              payload_json = excluded.payload_json,
              updated_at = excluded.updated_at
            """,
            (run_id, session_id, json.dumps(payload, ensure_ascii=False), updated_at),
        )

    @staticmethod
    def load_run_snapshot_payload(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT payload_json FROM run_snapshots WHERE run_id = ?", (run_id,)).fetchone()
        return SnapshotRepository._payload_from_row(row)

    @staticmethod
    def upsert_session_snapshot(
        conn: sqlite3.Connection,
        *,
        session_id: str,
        payload: dict[str, Any],
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO session_snapshots(session_id, payload_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              payload_json = excluded.payload_json,
              updated_at = excluded.updated_at
            """,
            (session_id, json.dumps(payload, ensure_ascii=False), updated_at),
        )

    @staticmethod
    def load_session_snapshot_payload(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT payload_json FROM session_snapshots WHERE session_id = ?", (session_id,)).fetchone()
        return SnapshotRepository._payload_from_row(row)

    @staticmethod
    def _payload_from_row(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
