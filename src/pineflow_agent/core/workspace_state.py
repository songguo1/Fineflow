"""Legacy split-file session state reader/writer for imports and exports."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from pineflow_agent.core.artifacts import ArtifactIndex
from pineflow_agent.core.file_state import workspace_file_state
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext, safe_workspace_name


class WorkspaceStateStore:
    """Read/write legacy split session files for one workspace session."""

    def __init__(self, workspace: WorkspaceContext) -> None:
        self.workspace = workspace

    def load(self) -> dict[str, Any] | None:
        manifest = self._read_json(self.workspace.manifest_path)
        if not manifest:
            return None
        return self._hydrate(manifest)

    def save(self, session: dict[str, Any]) -> dict[str, Any]:
        payload = make_json_safe(dict(session or {}))
        self.workspace.ensure_session_dirs()
        state_tree = dict(payload.get("state_tree") or {})
        steps = _trace_from_session(payload)
        events = [make_json_safe(dict(item)) for item in list(payload.get("events") or []) if isinstance(item, dict)]
        pending = {
            "status": str(payload.get("status") or "running"),
            "next_question": str(payload.get("next_question") or ""),
            "pending_task": dict(payload.get("pending_task") or {}),
            "repair": dict(payload.get("repair") or {}),
            "issues": list(payload.get("issues") or []),
            "risks": list(payload.get("risks") or []),
        }

        existing_events = self._read_jsonl(self.workspace.event_log_path)
        merged_events = _merge_event_logs(existing_events, events)
        if merged_events != existing_events:
            self._write_jsonl(self.workspace.event_log_path, merged_events)
        self._write_json(self.workspace.state_tree_path, state_tree)
        self._write_jsonl(self.workspace.steps_path, steps)
        self._write_json(self.workspace.pending_path, pending)
        self._write_layer_files(state_tree)

        artifacts = ArtifactIndex.for_workspace(self.workspace)
        manifest = self._manifest(payload, artifacts=artifacts)
        self._write_json(self.workspace.manifest_path, manifest)
        return self._hydrate(manifest)

    def _hydrate(self, manifest: dict[str, Any]) -> dict[str, Any]:
        state_tree = self._read_json(self.workspace.state_tree_path) or {}
        steps = self._read_jsonl(self.workspace.steps_path)
        pending = self._read_json(self.workspace.pending_path) or {}
        events = self._read_jsonl(self.workspace.event_log_path)
        artifacts = ArtifactIndex.for_workspace(self.workspace)
        result_summary = dict(manifest.get("result_summary") or {})
        status = str(result_summary.get("status") or manifest.get("status") or pending.get("status") or "running")
        updated_at = str(manifest.get("updated_at") or _utc_now())
        event_count = len(events)
        return make_json_safe(
            {
                "session_id": str(manifest.get("session_id") or self.workspace.session_id),
                "status": status,
                "success": bool(result_summary.get("success", status == "completed")),
                "final_message": str(result_summary.get("final_message") or ""),
                "messages": list(manifest.get("messages") or []),
                "request": dict(manifest.get("request") or {}),
                "events": events,
                "react_trace": steps,
                "state_tree": state_tree,
                "outputs": artifacts.outputs() or list(result_summary.get("outputs") or []),
                "logs": list(result_summary.get("logs") or []),
                "errors": list(result_summary.get("errors") or []),
                "next_question": str(pending.get("next_question") or result_summary.get("next_question") or ""),
                "issues": list(pending.get("issues") or []),
                "risks": list(pending.get("risks") or []),
                "pending_task": dict(pending.get("pending_task") or {}),
                "repair": dict(pending.get("repair") or {}),
                "transcript": dict(manifest.get("transcript") or {}),
                "file_state": workspace_file_state(
                    self.workspace,
                    artifacts=artifacts,
                    event_count=event_count,
                    updated_at=updated_at,
                ),
                "state_version": 2,
                "updated_at": updated_at,
                "event_count": event_count,
            }
        )

    def read_memory(self) -> str:
        """Read session_memory.md content, returning empty string if missing."""
        path = self.workspace.session_memory_path
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def write_memory(self, content: str) -> None:
        """Write content to session_memory.md (atomic overwrite)."""
        path = self.workspace.session_memory_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            temp_path.write_text(str(content or ""), encoding="utf-8")
            os.replace(temp_path, path)
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except PermissionError:
                pass

    def _manifest(
        self,
        session: dict[str, Any],
        *,
        artifacts: ArtifactIndex,
    ) -> dict[str, Any]:
        status = str(session.get("status") or "running")
        return make_json_safe(
            {
                "version": 2,
                "session_id": str(session.get("session_id") or self.workspace.session_id),
                "status": status,
                "messages": list(session.get("messages") or []),
                "transcript": dict(session.get("transcript") or {}),
                "request": dict(session.get("request") or {}),
                "paths": {
                    "events": str(self.workspace.event_log_path),
                    "state_tree": str(self.workspace.state_tree_path),
                    "steps": str(self.workspace.steps_path),
                    "pending": str(self.workspace.pending_path),
                    "artifacts": str(artifacts.path),
                    "layers": str(self.workspace.layers_dir),
                },
                "result_summary": {
                    "status": status,
                    "success": bool(session.get("success", status == "completed")),
                    "final_message": str(session.get("final_message") or ""),
                    "outputs": list(session.get("outputs") or []),
                    "logs": list(session.get("logs") or []),
                    "errors": list(session.get("errors") or []),
                    "next_question": str(session.get("next_question") or ""),
                },
                "updated_at": _utc_now(),
                "event_count": len(self._read_jsonl(self.workspace.event_log_path)),
            }
        )

    def _write_layer_files(self, state_tree: dict[str, Any]) -> None:
        self.workspace.layers_dir.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        for layer in list(state_tree.get("layers") or []):
            if not isinstance(layer, dict):
                continue
            layer_id = str(layer.get("layer_id") or layer.get("name") or "layer")
            file_name = f"{safe_workspace_name(layer_id)}.json"
            seen.add(file_name)
            self._write_json(self.workspace.layers_dir / file_name, dict(layer))
        for path in self.workspace.layers_dir.glob("*.json"):
            if path.name not in seen:
                try:
                    path.unlink()
                except OSError:
                    continue

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return make_json_safe(dict(value)) if isinstance(value, dict) else {}

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
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
                        items.append(make_json_safe(dict(value)))
        except OSError:
            return []
        return items

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            temp_path.write_text(json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_path, path)
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except PermissionError:
                pass

    @staticmethod
    def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(make_json_safe(item), ensure_ascii=False) + "\n" for item in items)
        path.write_text(text, encoding="utf-8")


def _trace_from_session(session: dict[str, Any]) -> list[dict[str, Any]]:
    trace = session.get("react_trace") or []
    return [make_json_safe(dict(item)) for item in list(trace) if isinstance(item, dict)]


def _merge_event_logs(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge snapshot events into the append-only event log without truncating it."""
    if not incoming:
        return list(existing)
    if not existing:
        return list(incoming)
    if incoming == existing[: len(incoming)]:
        return list(existing)
    if existing == incoming[: len(existing)]:
        return list(incoming)
    if incoming == existing[-len(incoming) :]:
        return list(existing)
    for overlap in range(min(len(existing), len(incoming)), 0, -1):
        if existing[-overlap:] == incoming[:overlap]:
            return list(existing) + list(incoming[overlap:])
    return list(existing) + [event for event in incoming if event not in existing]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
