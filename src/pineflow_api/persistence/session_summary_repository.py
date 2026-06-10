"""Session summary table SQL helpers for SessionStore."""

from __future__ import annotations

import sqlite3
from typing import Any


class SessionSummaryRepository:
    @staticmethod
    def count_sessions(conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()
        return int(row["count"] if row else 0)

    @staticmethod
    def get_session_bucket_state(conn: sqlite3.Connection, session_id: str) -> dict[str, str]:
        row = conn.execute(
            "SELECT archived_at, deleted_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return {}
        return {
            "archived_at": str(row["archived_at"] or ""),
            "deleted_at": str(row["deleted_at"] or ""),
        }

    @staticmethod
    def list_active_sessions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT session_id, status, first_message, updated_at, event_count, message_count
            FROM sessions
            WHERE archived_at = '' AND deleted_at = ''
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [
            {
                "session_id": str(row["session_id"] or ""),
                "status": str(row["status"] or ""),
                "first_message": str(row["first_message"] or ""),
                "updated_at": str(row["updated_at"] or ""),
                "event_count": int(row["event_count"] or 0),
                "message_count": int(row["message_count"] or 0),
            }
            for row in rows
        ]

    @staticmethod
    def update_bucket(conn: sqlite3.Connection, session_id: str, *, bucket: str, updated_at: str) -> None:
        column = "archived_at" if bucket == "archive" else "deleted_at"
        conn.execute(f"UPDATE sessions SET {column} = ?, updated_at = ? WHERE session_id = ?", (updated_at, updated_at, session_id))

    @staticmethod
    def update_status(conn: sqlite3.Connection, session_id: str, *, status: str, updated_at: str) -> None:
        conn.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?",
            (status, updated_at, session_id),
        )

    @staticmethod
    def upsert_summary(
        conn: sqlite3.Connection,
        *,
        session_id: str,
        status: str,
        session_status: str,
        first_message: str,
        message_count: int,
        event_count: int,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sessions(
              session_id, status, session_status, first_message, message_count,
              event_count, updated_at, archived_at, deleted_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, '', '')
            ON CONFLICT(session_id) DO UPDATE SET
              status = excluded.status,
              session_status = excluded.session_status,
              first_message = excluded.first_message,
              message_count = excluded.message_count,
              event_count = excluded.event_count,
              updated_at = excluded.updated_at
            """,
            (session_id, status, session_status, first_message, message_count, event_count, updated_at),
        )

    @staticmethod
    def ensure_session_row(
        conn: sqlite3.Connection,
        *,
        session_id: str,
        first_message: str,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sessions(
              session_id, status, session_status, first_message, message_count,
              event_count, updated_at, archived_at, deleted_at
            )
            VALUES(?, 'running', 'active', ?, ?, 0, ?, '', '')
            ON CONFLICT(session_id) DO UPDATE SET
              status = 'running',
              first_message = CASE
                WHEN sessions.first_message = '' THEN excluded.first_message
                ELSE sessions.first_message
              END,
              message_count = CASE
                WHEN sessions.message_count = 0 THEN excluded.message_count
                ELSE sessions.message_count
              END,
              updated_at = excluded.updated_at
            """,
            (session_id, first_message, 1 if first_message else 0, updated_at),
        )
