"""Execution memory for resumed runs and duplicate action suppression."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.models import ActionPlan, Observation, ReActStep
from pineflow_agent.tools.semantic.semantic_tools import is_semantic_action, normalize_semantic_input

SIGNATURE_FIELDS: dict[str, tuple[str, ...]] = {
    "csv_to_points": ("input_ref", "x_field", "y_field", "crs"),
    "reproject_layer": ("input_ref", "target_crs"),
    "buffer_layer": ("input_ref", "distance", "unit", "dissolve", "segments"),
    "clip_layer": ("input_ref", "overlay_ref"),
    "intersect_layer": ("input_ref", "overlay_ref"),
    "difference_layer": ("input_ref", "overlay_ref"),
    "union_layer": ("input_ref", "overlay_ref"),
    "extract_by_location": ("input_ref", "intersect_ref", "predicate"),
    "join_by_location": ("input_ref", "join_ref", "predicate", "join_fields"),
    "join_by_nearest": ("input_ref", "join_ref", "neighbors", "max_distance"),
    "fix_geometries": ("input_ref",),
    "export_result": ("layer_ref", "output_path"),
}


@dataclass(frozen=True)
class CompletedActionRecord:
    action: str
    signature: str
    step_index: int
    output_layer_id: str = ""
    output_path: str = ""


class ExecutionMemory:
    """Tracks completed action signatures so resumed runs can avoid redoing work."""

    def __init__(self) -> None:
        self._completed: dict[str, CompletedActionRecord] = {}

    @classmethod
    def from_steps(cls, steps: list[ReActStep]) -> "ExecutionMemory":
        memory = cls()
        for step in list(steps or []):
            memory.remember_step(step)
        return memory

    def remember_step(self, step: ReActStep) -> None:
        if not step.observation.is_success:
            return
        signature = action_signature(step.action, step.action_input)
        if not signature:
            return
        if signature in self._completed:
            return
        self._completed[signature] = CompletedActionRecord(
            action=step.action,
            signature=signature,
            step_index=int(step.index),
            output_layer_id=str(step.observation.output_layer_id or ""),
            output_path=str(step.observation.output_path or ""),
        )

    def has_completed(self, plan: ActionPlan) -> bool:
        signature = action_signature(plan.action, plan.action_input)
        return bool(signature and signature in self._completed)

    def record_for(self, plan: ActionPlan) -> CompletedActionRecord | None:
        signature = action_signature(plan.action, plan.action_input)
        if not signature:
            return None
        return self._completed.get(signature)

    def duplicate_observation(self, plan: ActionPlan) -> Observation:
        record = self.record_for(plan)
        if record is None:
            return Observation(
                status="success",
                message=f"Skipped duplicate GIS action {plan.action}; it already succeeded earlier in this workflow.",
                data={"skipped_duplicate": True, "action": plan.action},
            )

        detail = f"step {record.step_index}"
        if record.output_path:
            detail += f" with output {record.output_path}"
        elif record.output_layer_id:
            detail += f" with layer {record.output_layer_id}"
        return Observation(
            status="success",
            message=f"Skipped duplicate GIS action {plan.action}; the same grounded inputs already succeeded in {detail}.",
            output_layer_id=record.output_layer_id,
            output_path=record.output_path,
            data={
                "skipped_duplicate": True,
                "duplicate_of": {
                    "action": record.action,
                    "step_index": record.step_index,
                    "output_layer_id": record.output_layer_id,
                    "output_path": record.output_path,
                },
            },
        )


def action_signature(action: str, action_input: dict[str, Any]) -> str:
    fields = SIGNATURE_FIELDS.get(str(action or "").strip())
    if not fields:
        return ""
    normalized = _normalized_action_input(str(action or "").strip(), action_input)
    payload = {
        field: normalized.get(field)
        for field in fields
        if normalized.get(field) is not None and normalized.get(field) != ""
    }
    if not payload:
        return ""
    return json.dumps(
        make_json_safe({"action": str(action or "").strip(), "inputs": payload}),
        ensure_ascii=False,
        sort_keys=True,
    )


def _normalized_action_input(action: str, action_input: dict[str, Any]) -> dict[str, Any]:
    if is_semantic_action(action):
        return normalize_semantic_input(action, action_input)
    return dict(action_input or {})
