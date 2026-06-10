"""Session/run event SQL helpers for SessionStore."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from pineflow_api.contracts.run_events import normalize_run_event


class EventRepository:
    @staticmethod
    def payload_from_row(row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return normalize_run_event(
            dict(payload),
            session_id=str(row["session_id"] or ""),
            run_id=str(row["run_id"] or ""),
            seq=int(row["seq"] or 0),
            created_at=str(row["created_at"] or ""),
        )

    @staticmethod
    def row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        payload = EventRepository.payload_from_row(row)
        return {
            "session_id": str(row["session_id"] or ""),
            "seq": int(row["seq"] or 0),
            "run_id": str(row["run_id"] or ""),
            "event_type": str(row["event_type"] or ""),
            "created_at": str(row["created_at"] or ""),
            "payload": payload,
        }

    @staticmethod
    def list_session_events(
        conn: sqlite3.Connection,
        session_id: str,
        *,
        after_seq: int = 0,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if limit is None:
            rows = conn.execute(
                """
                SELECT session_id, seq, run_id, event_type, payload_json, created_at
                FROM session_events
                WHERE session_id = ?
                ORDER BY seq
                """,
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT session_id, seq, run_id, event_type, payload_json, created_at
                FROM session_events
                WHERE session_id = ? AND seq > ?
                ORDER BY seq
                LIMIT ?
                """,
                (session_id, after_seq, limit),
            ).fetchall()
        return [EventRepository.row_to_record(row) for row in rows]

    @staticmethod
    def list_run_events(
        conn: sqlite3.Connection,
        run_id: str,
        *,
        after_seq: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT session_id, seq, run_id, event_type, payload_json, created_at
            FROM session_events
            WHERE run_id = ? AND seq > ?
            ORDER BY seq
            LIMIT ?
            """,
            (run_id, after_seq, limit),
        ).fetchall()
        return [EventRepository.row_to_record(row) for row in rows]

    @staticmethod
    def count_session_events(conn: sqlite3.Connection, session_id: str) -> int:
        row = conn.execute("SELECT COUNT(*) AS count FROM session_events WHERE session_id = ?", (session_id,)).fetchone()
        return int(row["count"] if row else 0)

    @staticmethod
    def next_session_seq(conn: sqlite3.Connection, session_id: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM session_events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["next_seq"] if row else 1)

    @staticmethod
    def insert_event(
        conn: sqlite3.Connection,
        *,
        session_id: str,
        run_id: str,
        seq: int,
        event_type: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO session_events(session_id, run_id, seq, event_type, payload_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (session_id, run_id, seq, event_type, json.dumps(payload, ensure_ascii=False), created_at),
        )

    @staticmethod
    def replace_session_events(
        conn: sqlite3.Connection,
        *,
        session_id: str,
        events: list[dict[str, Any]],
        run_id: str,
        created_at: str,
    ) -> None:
        conn.execute("DELETE FROM session_events WHERE session_id = ?", (session_id,))
        for index, event in enumerate(events, start=1):
            stored_event = normalize_run_event(
                dict(event),
                session_id=session_id,
                run_id=str(event.get("run_id") or run_id or ""),
                seq=index,
                created_at=created_at,
            )
            EventRepository.insert_event(
                conn,
                session_id=session_id,
                run_id=str(stored_event.get("run_id") or ""),
                seq=index,
                event_type=str(stored_event.get("event_type") or stored_event.get("event") or ""),
                payload=stored_event,
                created_at=created_at,
            )
