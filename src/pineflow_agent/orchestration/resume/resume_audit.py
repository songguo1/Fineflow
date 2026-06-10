"""Shared resume audit and repair helpers."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.models import ActionPlan, Observation
from pineflow_agent.core.state_tree import GISStateTree


def repair_steps_from_payload(repair: dict) -> list[dict]:
    steps = [dict(step) for step in list(repair.get("steps") or []) if isinstance(step, dict)]
    if steps:
        return steps
    action = repair.get("action")
    if isinstance(action, dict) and action:
        return [dict(action)]
    return []


def alias_repaired_layer_refs(state: GISStateTree, *, pending_task: dict, patch: dict) -> None:
    filled_slots = dict(pending_task.get("filled_slots") or {})
    for slot, replacement_ref in dict(patch or {}).items():
        if not _looks_like_layer_slot(str(slot)):
            continue
        original_ref = str(filled_slots.get(slot) or "").strip()
        replacement = str(replacement_ref or "").strip()
        if not original_ref or not replacement or original_ref == replacement:
            continue
        try:
            original = state.resolve(original_ref)
            repaired = state.resolve(replacement)
        except KeyError:
            continue
        for alias in {original_ref, original.layer_id, original.name}:
            if alias:
                state.set_alias(alias, repaired.layer_id)


def confirmed_decision_audit(pending_task: dict, *, repair: dict | None = None) -> dict[str, Any]:
    risk = dict(pending_task.get("risk") or {})
    recommendation = _crs_recommendation(pending_task)
    return {
        "decision": "user_confirmed",
        "risk_code": str(pending_task.get("risk_code") or risk.get("code") or ""),
        "risk_category": str(pending_task.get("confirmation_type") or risk.get("category") or ""),
        "message": risk_message(pending_task),
        "active_intent": str(pending_task.get("active_intent") or ""),
        "crs_recommendation": make_json_safe(recommendation),
        "selected_crs": _selected_crs_from_repair(repair, recommendation),
        "repair": make_json_safe(dict(repair or {})),
    }


def resume_decision_audit(pending_task: dict, *, plan: ActionPlan) -> dict[str, Any]:
    risk = dict(pending_task.get("risk") or {})
    if not risk and not pending_task.get("risk_code"):
        return {}
    recommendation = _crs_recommendation(pending_task)
    selected_choices = _selected_choices_for_patch(pending_task, dict(plan.action_input or {}))
    slot_patch = _slot_patch_from_plan(pending_task, plan)
    return {
        "decision": "user_supplied_resolution",
        "risk_code": str(pending_task.get("risk_code") or risk.get("code") or ""),
        "risk_category": str(pending_task.get("confirmation_type") or risk.get("category") or ""),
        "message": risk_message(pending_task),
        "active_intent": str(pending_task.get("active_intent") or plan.action or ""),
        "crs_recommendation": make_json_safe(recommendation),
        "selected_crs": _selected_crs_from_plan(plan, recommendation),
        "slot_patch": make_json_safe(slot_patch),
        "selected_choices": make_json_safe(selected_choices),
        "resolved_action": plan.to_dict(),
    }


def risk_message(pending_task: dict) -> str:
    risk = dict(pending_task.get("risk") or {})
    return str(
        pending_task.get("ux_explanation")
        or risk.get("message")
        or pending_task.get("last_question")
        or ""
    )


def repair_input_snapshot(state: GISStateTree, repair_plan: ActionPlan) -> dict[str, Any]:
    layer_ref = str(dict(repair_plan.action_input or {}).get("input_ref") or "").strip()
    if not layer_ref:
        return {}
    return layer_snapshot(state, layer_ref)


def repair_audit(
    state: GISStateTree,
    repair_plan: ActionPlan,
    repair_observation: Observation,
    *,
    before_snapshot: dict[str, Any],
    reason: str,
    decision: str,
) -> dict[str, Any]:
    layer = dict(dict(repair_observation.data or {}).get("layer") or {})
    output_ref = str(layer.get("name") or repair_observation.output_layer_id or "").strip()
    after_snapshot = layer_snapshot(state, output_ref) if output_ref else observation_layer_snapshot(repair_observation)
    return {
        "decision": decision,
        "action": repair_plan.action,
        "reason": reason,
        "input": before_snapshot,
        "output": after_snapshot,
        "feature_count_before": before_snapshot.get("feature_count"),
        "feature_count_after": after_snapshot.get("feature_count"),
    }


def append_observation_audit(observation: Observation, key: str, item: dict[str, Any]) -> None:
    if not item:
        return
    data = dict(observation.data or {})
    existing = [dict(value) for value in list(data.get(key) or []) if isinstance(value, dict)]
    existing.append(make_json_safe(dict(item)))
    data[key] = existing
    observation.data = data


def repair_success_message(audit: dict[str, Any]) -> str:
    input_name = str(dict(audit.get("input") or {}).get("name") or "输入图层")
    output_name = str(dict(audit.get("output") or {}).get("name") or "修复结果")
    before = audit.get("feature_count_before")
    after = audit.get("feature_count_after")
    if before is not None and after is not None:
        return f"已按确认修复 {input_name}，生成 {output_name}；要素数从 {before} 变为 {after}，后续分析将继续使用修复后的图层。"
    return f"已按确认修复 {input_name}，生成 {output_name}，后续分析将继续使用修复后的图层。"


def layer_snapshot(state: GISStateTree, layer_ref: str) -> dict[str, Any]:
    try:
        layer = state.resolve(layer_ref)
    except KeyError:
        return {"ref": str(layer_ref or "")}
    metadata = dict(layer.metadata or {})
    return {
        "layer_id": layer.layer_id,
        "name": layer.name,
        "kind": layer.kind,
        "source": layer.source,
        "crs": metadata.get("crs"),
        "geometry_type": metadata.get("geometry_type"),
        "feature_count": metadata.get("feature_count", metadata.get("row_count")),
    }


def observation_layer_snapshot(observation: Observation) -> dict[str, Any]:
    layer = dict(dict(observation.data or {}).get("layer") or {})
    metadata = dict(layer.get("metadata") or {})
    return {
        "layer_id": str(layer.get("layer_id") or observation.output_layer_id or ""),
        "name": str(layer.get("name") or observation.output_layer_id or ""),
        "kind": str(layer.get("kind") or ""),
        "source": str(layer.get("source") or observation.output_path or ""),
        "crs": metadata.get("crs"),
        "geometry_type": metadata.get("geometry_type"),
        "feature_count": metadata.get("feature_count", metadata.get("row_count")),
    }


def _looks_like_layer_slot(slot: str) -> bool:
    return slot.endswith("_ref") or slot.endswith("_refs") or slot in {"layer_ref", "input_ref"}


def _crs_recommendation(pending_task: dict[str, Any]) -> dict[str, Any]:
    risk = dict(pending_task.get("risk") or {})
    diagnosis = dict(risk.get("diagnosis") or {})
    recommendation = diagnosis.get("crs_recommendation")
    return dict(recommendation) if isinstance(recommendation, dict) else {}


def _selected_crs_from_repair(repair: dict | None, recommendation: dict[str, Any]) -> str:
    payload = dict(repair or {})
    action = dict(payload.get("action") or {}) if isinstance(payload.get("action"), dict) else {}
    action_input = dict(action.get("action_input") or {}) if isinstance(action.get("action_input"), dict) else {}
    target = str(action_input.get("target_crs") or "").strip()
    if target:
        return target
    steps = [dict(step) for step in list(payload.get("steps") or []) if isinstance(step, dict)]
    for step in steps:
        step_input = dict(step.get("action_input") or {})
        target = str(step_input.get("target_crs") or "").strip()
        if target:
            return target
    return str(recommendation.get("target_crs") or recommendation.get("recommended_crs") or "").strip()


def _selected_crs_from_plan(plan: ActionPlan, recommendation: dict[str, Any]) -> str:
    target = str(dict(plan.action_input or {}).get("target_crs") or "").strip()
    if target:
        return target
    return str(recommendation.get("target_crs") or recommendation.get("recommended_crs") or "").strip()


def _slot_patch_from_plan(pending_task: dict[str, Any], plan: ActionPlan) -> dict[str, Any]:
    filled = dict(pending_task.get("filled_slots") or {})
    action_input = dict(plan.action_input or {})
    patch: dict[str, Any] = {}
    for key, value in action_input.items():
        if filled.get(key) != value:
            patch[key] = value
    return patch


def _selected_choices_for_patch(pending_task: dict[str, Any], action_input: dict[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for choice in list(pending_task.get("choices") or []):
        if not isinstance(choice, dict):
            continue
        slot = str(choice.get("slot") or "").strip()
        if not slot or slot not in action_input:
            continue
        if choice.get("value") == action_input.get(slot):
            selected.append(dict(choice))
    return selected
