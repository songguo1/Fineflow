"""In-process run manager for PineFlow runtime workers."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock, Thread
from typing import Callable

from pineflow_api.application.run_service import RunContext, RunService
from pineflow_api.contracts.run_lifecycle import RunStatus


RunExecute = Callable[[], dict]
RunErrorHandler = Callable[[Exception], None]


@dataclass
class RunWorker:
    run: RunContext
    execute: RunExecute
    on_error: RunErrorHandler
    on_done: Callable[[str], None]
    thread: Thread | None = None

    def start(self) -> None:
        self.thread = Thread(target=self._run, daemon=True, name=f"pineflow-run-{self.run.run_id[:8]}")
        self.thread.start()

    def _run(self) -> None:
        try:
            self.execute()
        except Exception as exc:  # pragma: no cover - defensive background guard
            self.on_error(exc)
        finally:
            self.on_done(self.run.run_id)


class RunManager:
    """Owns background worker lifecycle and delegates persistence to RunService."""

    def __init__(self, runs: RunService) -> None:
        self.runs = runs
        self._lock = Lock()
        self._workers: dict[str, RunWorker] = {}

    def start(self, run: RunContext, *, execute: RunExecute, on_error: RunErrorHandler) -> dict:
        worker = RunWorker(run=run, execute=execute, on_error=on_error, on_done=self._forget)
        with self._lock:
            self._workers[run.run_id] = worker
        worker.start()
        return {"session_id": run.session_id, "run_id": run.run_id, "status": RunStatus.RUNNING}

    def request_pause(self, run_id: str) -> dict:
        return self.runs.request_pause(run_id)

    def request_cancel(self, run_id: str) -> dict:
        return self.runs.request_cancel(run_id)

    def mark_resumed(self, run_id: str) -> None:
        self.runs.mark_resumed(run_id)

    def should_pause_session(self, session_id: str) -> bool:
        return self.runs.should_pause_session(session_id)

    def should_cancel_session(self, session_id: str) -> bool:
        return self.runs.should_cancel_session(session_id)

    def _forget(self, run_id: str) -> None:
        with self._lock:
            self._workers.pop(run_id, None)
