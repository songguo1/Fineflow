"""Run lifecycle SQL helpers for SessionStore."""

from __future__ import annotations

import sqlite3
from typing import Any


class RunRepository:
    @staticmethod
    def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "run_id": str(row["run_id"] or ""),
            "session_id": str(row["session_id"] or ""),
            "status": str(row["status"] or ""),
            "route_kind": str(row["route_kind"] or ""),
            "message": str(row["message"] or ""),
            "started_at": str(row["started_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
            "result_status": str(row["result_status"] or ""),
            "error": str(row["error"] or ""),
        }

    @staticmethod
    def insert_run(
        conn: sqlite3.Connection,
        *,
        run_id: str,
        session_id: str,
        status: str,
        route_kind: str,
        message: str,
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO session_runs(
              run_id, session_id, status, route_kind, message,
              started_at, updated_at, completed_at, result_status, error
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, '', '', '')
            """,
            (run_id, session_id, status, route_kind, message, now, now),
        )

    @staticmethod
    def update_finished_run(
        conn: sqlite3.Connection,
        *,
        run_id: str,
        status: str,
        error: str,
        updated_at: str,
        completed_at: str,
    ) -> None:
        conn.execute(
            """
            UPDATE session_runs
            SET status = ?, result_status = ?, error = ?, updated_at = ?, completed_at = ?
            WHERE run_id = ?
            """,
            (status, status, error, updated_at, completed_at, run_id),
        )

    @staticmethod
    def update_requested_status(
        conn: sqlite3.Connection,
        *,
        run_id: str,
        status: str,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            UPDATE session_runs
            SET status = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (status, updated_at, run_id),
        )

    @staticmethod
    def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT run_id, session_id, status, route_kind, message,
                   started_at, updated_at, completed_at, result_status, error
            FROM session_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        return RunRepository.row_to_dict(row)

    @staticmethod
    def list_runs(conn: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT run_id, session_id, status, route_kind, message,
                   started_at, updated_at, completed_at, result_status, error
            FROM session_runs
            WHERE session_id = ?
            ORDER BY started_at DESC
            """,
            (session_id,),
        ).fetchall()
        return [RunRepository.row_to_dict(row) for row in rows]

    @staticmethod
    def latest_run_for_session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT run_id, session_id, status, route_kind, message,
                   started_at, updated_at, completed_at, result_status, error
            FROM session_runs
            WHERE session_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return RunRepository.row_to_dict(row)

    @staticmethod
    def session_id_for_run(conn: sqlite3.Connection, run_id: str) -> str:
        row = conn.execute("SELECT session_id FROM session_runs WHERE run_id = ?", (run_id,)).fetchone()
        return str(row["session_id"] or "") if row is not None else ""
