"""Structured state queries for non-execution GIS answers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pineflow_agent.core.artifacts import ArtifactRecord

from pineflow_api.persistence.session_state import SessionState
from pineflow_api.routing.turn_intent import AnswerType


@dataclass(frozen=True)
class StateSummaryCounts:
    layers: int = 0
    outputs: int = 0
    intermediate_outputs: int = 0
    react_trace: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "layers": self.layers,
            "outputs": self.outputs,
            "intermediate_outputs": self.intermediate_outputs,
            "react_trace": self.react_trace,
        }


@dataclass(frozen=True)
class StateQueryResult:
    answer_type: str
    layers: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    intermediate_outputs: list[dict[str, Any]] = field(default_factory=list)
    legacy_trace_outputs: list[dict[str, Any]] = field(default_factory=list)
    last_step: dict[str, Any] = field(default_factory=dict)
    summary_counts: StateSummaryCounts = field(default_factory=StateSummaryCounts)
    has_state: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_type": self.answer_type,
            "layers": [dict(item) for item in self.layers],
            "outputs": [dict(item) for item in self.outputs],
            "intermediate_outputs": [dict(item) for item in self.intermediate_outputs],
            "legacy_trace_outputs": [dict(item) for item in self.legacy_trace_outputs],
            "last_step": dict(self.last_step),
            "summary_counts": self.summary_counts.to_dict(),
            "has_state": self.has_state,
        }


class StateQueryService:
    """Return structured state facts without rendering natural language."""

    def query(self, answer_type: AnswerType, session_state: SessionState) -> StateQueryResult:
        state_tree = session_state.state_tree
        layers = _layers(state_tree)
        outputs = _outputs(session_state, state_tree)
        intermediate_outputs = _intermediate_outputs(session_state, state_tree)
        trace = session_state.react_trace
        # Keep trace-derived outputs as explicit legacy fallback so callers can
        # prefer artifact/state outputs and only dip into trace when old data lacks them.
        legacy_trace_outputs = _outputs_from_trace(trace)
        return StateQueryResult(
            answer_type=str(answer_type or "summary"),
            layers=layers,
            outputs=outputs,
            intermediate_outputs=intermediate_outputs,
            legacy_trace_outputs=legacy_trace_outputs,
            last_step=_last_successful_step(trace),
            summary_counts=StateSummaryCounts(
                layers=len(layers),
                outputs=len(outputs),
                intermediate_outputs=len(intermediate_outputs),
                react_trace=len(trace),
            ),
            has_state=bool(layers or outputs or intermediate_outputs or trace),
        )

    def outputs(self, session_state: SessionState, state_tree: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return _outputs(session_state, session_state.state_tree if state_tree is None else dict(state_tree or {}))


def _outputs(session_state: SessionState, state_tree: dict[str, Any]) -> list[dict[str, Any]]:
    del state_tree
    artifacts = _outputs_from_artifacts(session_state.artifacts, include_intermediate=False)
    if artifacts:
        return artifacts
    existing = session_state.outputs
    if isinstance(existing, list) and existing:
        return [dict(item) for item in existing if isinstance(item, dict) and _is_final_output(dict(item))]
    return []


def _intermediate_outputs(session_state: SessionState, state_tree: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = _outputs_from_artifacts(session_state.artifacts, include_intermediate=True)
    intermediates = [item for item in artifacts if str(item.get("role") or "") == "intermediate"]
    if intermediates:
        return intermediates
    return [
        layer
        for layer in _layers(state_tree)
        if not _is_input_layer(layer) and not _is_final_output(layer)
    ]


def _outputs_from_artifacts(artifacts: list[dict[str, Any]], *, include_intermediate: bool = False) -> list[dict[str, Any]]:
    records: list[ArtifactRecord] = []
    for artifact in artifacts:
        record = ArtifactRecord.from_dict(dict(artifact))
        role = str(record.role or "")
        if role == "input" or (role == "intermediate" and not include_intermediate):
            continue
        path = str(record.path or "")
        if not path:
            continue
        records.append(record)
    records.sort(
        key=lambda item: (
            _artifact_role_rank(item.role),
            item.source_step if item.source_step is not None else 10**9,
            str(item.created_at or ""),
            str(item.name or ""),
        )
    )
    return [record.output_dict() for record in records]


def _outputs_from_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback extractor for older sessions that do not have artifact-backed outputs."""
    outputs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step in trace:
        observation = dict(step.get("observation") or {})
        output_path = str(observation.get("output_path") or "")
        output_layer_id = str(observation.get("output_layer_id") or "")
        if _is_temp_path(output_path):
            continue
        key = output_path or output_layer_id
        if not key or key in seen:
            continue
        seen.add(key)
        outputs.append(
            {
                "layer_id": output_layer_id,
                "name": output_layer_id or str(step.get("action") or "output"),
                "path": output_path,
                "kind": "",
            }
        )
    return outputs


def _last_successful_step(trace: list[dict[str, Any]]) -> dict[str, Any]:
    for step in reversed(trace):
        observation = dict(step.get("observation") or {})
        if str(observation.get("status") or "") == "success":
            return dict(step)
    return {}


def _layers(state_tree: dict[str, Any]) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    for layer in list((state_tree or {}).get("layers") or []):
        if not isinstance(layer, dict):
            continue
        payload = dict(layer)
        metadata = dict(payload.get("metadata") or {})
        artifact = dict(metadata.get("artifact") or {})
        if artifact:
            for source_key, target_key in (
                ("artifact_id", "artifact_id"),
                ("role", "artifact_role"),
                ("reusable", "artifact_reusable"),
                ("materialized", "artifact_materialized"),
                ("file_name", "file_name"),
                ("input_layer_names", "input_layer_names"),
                ("input_layer_ids", "input_layer_ids"),
                ("input_artifact_ids", "input_artifact_ids"),
                ("input_artifacts", "input_artifacts"),
                ("parameters", "parameters"),
                ("summary_lines", "summary_lines"),
                ("source_action", "source_action"),
                ("source_step", "source_step"),
                ("source_run_id", "source_run_id"),
                ("display_title", "display_title"),
                ("display_summary", "display_summary"),
            ):
                if target_key not in payload and source_key in artifact:
                    payload[target_key] = artifact.get(source_key)
            if "lineage" not in payload and isinstance(artifact.get("lineage"), dict):
                payload["lineage"] = dict(artifact.get("lineage") or {})
        layers.append(payload)
    return layers


def _item_path(item: dict[str, Any]) -> str:
    return str(item.get("path") or item.get("output_path") or item.get("source") or "").strip()


def _is_temp_path(path: str) -> bool:
    normalized = str(path or "").replace("/", "\\").lower()
    return "\\.pineflow\\sessions\\" in normalized and "\\temp\\" in normalized


def _is_final_output(output: dict[str, Any]) -> bool:
    role = str(output.get("role") or "").lower()
    algorithm_id = str(output.get("algorithm_id") or "").lower()
    path = _item_path(output)
    return role == "final" or algorithm_id == "export_result" or (bool(path) and not _is_temp_path(path) and role != "intermediate")


def _is_input_layer(layer: dict[str, Any]) -> bool:
    algorithm_id = str(layer.get("algorithm_id") or "").strip()
    parent_ids = layer.get("parent_ids") or []
    source = _item_path(layer)
    return not algorithm_id and not parent_ids and not _is_temp_path(source)


def _artifact_role_rank(role: str) -> int:
    return {"final": 0, "report": 1, "intermediate": 2, "input": 3}.get(str(role or "").lower(), 9)
