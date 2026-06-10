"""Compact prompt context for GIS ReAct model calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe


MAX_RECENT_STEPS = 8
MAX_FIELDS_PER_LAYER = 20
MAX_TEXT_LENGTH = 800
MAX_GENERIC_LIST_ITEMS = 20
MAX_GENERIC_DICT_ITEMS = 30
MAX_WORKSPACE_LAYERS = 10
MAX_WORKSPACE_ARTIFACTS = 6
MAX_WORKSPACE_RISKS = 5

_LAYER_KEYS = ("layer_id", "name", "kind", "source", "parent_ids", "algorithm_id")
_METADATA_KEYS = (
    "crs",
    "geometry_type",
    "feature_count",
    "row_count",
    "provider",
    "storage_type",
    "encoding",
)
_OMITTED_OBSERVATION_DATA_KEYS = {"qgis_result", "state_tree", "react_trace", "steps"}


def build_workspace_snapshot(
    *,
    user_request: str = "",
    state: dict[str, Any] | None = None,
    previous_steps: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    tool_disclosure: dict[str, Any] | None = None,
    suggested_skills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a compact, agent-oriented workspace view for action selection."""

    compact_state = compact_state_tree(dict(state or {}))
    compact_steps = compact_steps_for_snapshot(list(previous_steps or []))
    layer_items = [_snapshot_layer(layer) for layer in list(compact_state.get("layers") or []) if isinstance(layer, dict)]
    artifact_items = relevant_artifacts_for_snapshot(
        list(artifacts or []),
        user_request=user_request,
        max_items=MAX_WORKSPACE_ARTIFACTS,
    )
    risks = unresolved_risks_for_snapshot(compact_steps)
    disclosure = dict(tool_disclosure or {})
    snapshot = {
        "summary": {
            "layer_count": len(layer_items),
            "artifact_count": len([item for item in list(artifacts or []) if isinstance(item, dict)]),
            "recent_step_count": len(compact_steps),
            "risk_count": len(risks),
        },
        "layers": layer_items[:MAX_WORKSPACE_LAYERS],
        "relevant_artifacts": artifact_items,
        "recent_successful_outputs": recent_successful_outputs_for_snapshot(compact_steps),
        "unresolved_risks": risks,
        "active_toolkits": list(disclosure.get("active_toolkits") or []),
    }
    skill_focus = skill_focus_for_snapshot(list(suggested_skills or []))
    if skill_focus:
        snapshot["skill_focus"] = skill_focus
    return make_json_safe(snapshot)


def compact_steps_for_snapshot(previous_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return compact_steps(previous_steps, max_recent_steps=MAX_RECENT_STEPS)


def compact_state_tree(
    state: dict[str, Any],
    *,
    max_fields_per_layer: int = MAX_FIELDS_PER_LAYER,
) -> dict[str, Any]:
    """Return a lightweight state tree suitable for LLM prompt context."""

    safe_state = make_json_safe(dict(state or {}))
    compact: dict[str, Any] = {"layers": []}
    for layer in list(safe_state.get("layers") or []):
        if isinstance(layer, dict):
            compact["layers"].append(compact_layer(layer, max_fields_per_layer=max_fields_per_layer))

    aliases = safe_state.get("aliases")
    if isinstance(aliases, dict):
        compact["aliases"] = {str(key): str(value) for key, value in aliases.items()}
    return compact


def compact_steps(
    previous_steps: list[dict[str, Any]],
    *,
    max_recent_steps: int = MAX_RECENT_STEPS,
    max_fields_per_layer: int = MAX_FIELDS_PER_LAYER,
) -> list[dict[str, Any]]:
    """Keep only recent ReAct steps and compact heavy observations."""

    steps = [step for step in list(previous_steps or []) if isinstance(step, dict)]
    if max_recent_steps > 0:
        steps = steps[-max_recent_steps:]

    return [
        compact_step(step, max_fields_per_layer=max_fields_per_layer)
        for step in steps
    ]


def compact_step(
    step: dict[str, Any],
    *,
    max_fields_per_layer: int = MAX_FIELDS_PER_LAYER,
) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "index": step.get("index"),
        "action": step.get("action"),
        "action_input": compact_value(step.get("action_input") or {}),
    }
    thought = str(step.get("thought") or "").strip()
    if thought:
        compact["thought"] = _truncate_text(thought)
    if step.get("attempt_no") is not None:
        compact["attempt_no"] = step.get("attempt_no")

    observation = step.get("observation")
    if isinstance(observation, dict):
        compact["observation"] = compact_observation(
            observation,
            max_fields_per_layer=max_fields_per_layer,
        )
    return compact


def compact_observation(
    observation: dict[str, Any],
    *,
    max_fields_per_layer: int = MAX_FIELDS_PER_LAYER,
) -> dict[str, Any]:
    safe_observation = make_json_safe(dict(observation or {}))
    compact: dict[str, Any] = {}
    for key in ("status", "message", "output_layer_id", "output_path"):
        value = safe_observation.get(key)
        if value in (None, ""):
            continue
        compact[key] = _truncate_text(value) if key == "message" else value

    data = safe_observation.get("data")
    if isinstance(data, dict):
        compact_data = compact_observation_data(data, max_fields_per_layer=max_fields_per_layer)
        if compact_data:
            compact["data"] = compact_data
    return compact


def compact_observation_data(
    data: dict[str, Any],
    *,
    max_fields_per_layer: int = MAX_FIELDS_PER_LAYER,
) -> dict[str, Any]:
    """Keep model-useful tool feedback while dropping bulky runtime payloads."""

    compact: dict[str, Any] = {}
    for key, value in data.items():
        if key in _OMITTED_OBSERVATION_DATA_KEYS:
            continue
        if key == "layer" and isinstance(value, dict):
            compact[key] = compact_layer(value, max_fields_per_layer=max_fields_per_layer)
            continue
        if key == "layers" and isinstance(value, list):
            compact[key] = [
                compact_layer(item, max_fields_per_layer=max_fields_per_layer)
                for item in value[:MAX_GENERIC_LIST_ITEMS]
                if isinstance(item, dict)
            ]
            continue
        compact[key] = compact_value(value)
    return compact


def compact_layer(
    layer: dict[str, Any],
    *,
    max_fields_per_layer: int = MAX_FIELDS_PER_LAYER,
) -> dict[str, Any]:
    safe_layer = make_json_safe(dict(layer or {}))
    compact = {
        key: safe_layer.get(key)
        for key in _LAYER_KEYS
        if safe_layer.get(key) not in (None, "")
    }

    metadata = safe_layer.get("metadata")
    if isinstance(metadata, dict):
        compact_metadata = compact_layer_metadata(
            metadata,
            max_fields_per_layer=max_fields_per_layer,
        )
        if compact_metadata:
            compact["metadata"] = compact_metadata
    return compact


def compact_layer_metadata(
    metadata: dict[str, Any],
    *,
    max_fields_per_layer: int = MAX_FIELDS_PER_LAYER,
) -> dict[str, Any]:
    safe_metadata = make_json_safe(dict(metadata or {}))
    compact: dict[str, Any] = {}
    for key in _METADATA_KEYS:
        value = safe_metadata.get(key)
        if value not in (None, ""):
            compact[key] = value

    fields = safe_metadata.get("fields")
    if isinstance(fields, list):
        compact["fields"] = [str(field) for field in fields[:max_fields_per_layer]]
        compact["field_count"] = len(fields)
    elif safe_metadata.get("field_count") is not None:
        compact["field_count"] = safe_metadata.get("field_count")

    artifact = safe_metadata.get("artifact")
    if isinstance(artifact, dict):
        compact_artifact = {
            key: artifact.get(key)
            for key in ("artifact_id", "role", "name", "file_name", "source_step", "source_action", "algorithm_id")
            if artifact.get(key) not in (None, "")
        }
        if compact_artifact:
            compact["artifact"] = compact_artifact

    for key, value in safe_metadata.items():
        if key in compact or key in {"fields", "artifact"}:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            compact[key] = _truncate_text(value) if isinstance(value, str) else value
    return compact


def relevant_artifacts_for_snapshot(
    artifacts: list[dict[str, Any]],
    *,
    user_request: str = "",
    max_items: int = MAX_WORKSPACE_ARTIFACTS,
) -> list[dict[str, Any]]:
    candidates = [dict(item) for item in list(artifacts or []) if isinstance(item, dict)]
    scored = sorted(
        ((_artifact_relevance_score(item, user_request), index, item) for index, item in enumerate(candidates)),
        key=lambda item: (item[0], _source_step_sort_value(item[2]), item[1]),
        reverse=True,
    )
    return [_snapshot_artifact(item) for score, _, item in scored[:max_items] if score > 0]


def recent_successful_outputs_for_snapshot(previous_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for step in list(previous_steps or [])[-MAX_RECENT_STEPS:]:
        observation = step.get("observation") if isinstance(step, dict) else {}
        if not isinstance(observation, dict) or str(observation.get("status") or "") != "success":
            continue
        output_layer_id = str(observation.get("output_layer_id") or "").strip()
        output_path = str(observation.get("output_path") or "").strip()
        data = dict(observation.get("data") or {})
        layer = dict(data.get("layer") or {})
        if not output_layer_id and not output_path and not layer:
            continue
        outputs.append(
            {
                "step_index": step.get("index"),
                "action": step.get("action"),
                "layer_id": output_layer_id or str(layer.get("layer_id") or ""),
                "name": str(layer.get("name") or output_layer_id or ""),
                "path": output_path or str(layer.get("source") or ""),
                "file_name": Path(output_path or str(layer.get("source") or "")).name if (output_path or layer.get("source")) else "",
            }
        )
    return make_json_safe(outputs[-5:])


def unresolved_risks_for_snapshot(previous_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for step in list(previous_steps or [])[-MAX_RECENT_STEPS:]:
        if not isinstance(step, dict):
            continue
        observation = step.get("observation")
        if not isinstance(observation, dict):
            continue
        data = dict(observation.get("data") or {})
        for source_key in ("preflight_warnings", "postflight_warnings", "warnings", "quality_findings"):
            for item in list(data.get(source_key) or []):
                if not isinstance(item, dict):
                    continue
                risks.append(_snapshot_risk(item, source=source_key, action=str(step.get("action") or ""), step_index=step.get("index")))
    return make_json_safe(risks[-MAX_WORKSPACE_RISKS:])


def skill_focus_for_snapshot(suggested_skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    focus: list[dict[str, Any]] = []
    for skill in list(suggested_skills or [])[:3]:
        if not isinstance(skill, dict):
            continue
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        item = {
            "name": name,
            "workspace_attention": list(skill.get("workspace_attention") or [])[:5],
            "risk_awareness": list(skill.get("risk_awareness") or [])[:5],
            "default_preferences": list(skill.get("default_preferences") or [])[:5],
            "workspace_queries": list(skill.get("workspace_queries") or [])[:5],
        }
        focus.append({key: value for key, value in item.items() if value})
    return focus


def _snapshot_layer(layer: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(layer.get("metadata") or {})
    artifact = dict(metadata.get("artifact") or {})
    payload = {
        "layer_id": layer.get("layer_id"),
        "name": layer.get("name"),
        "kind": layer.get("kind"),
        "crs": metadata.get("crs"),
        "geometry_type": metadata.get("geometry_type"),
        "feature_count": metadata.get("feature_count"),
        "field_count": metadata.get("field_count"),
        "fields": list(metadata.get("fields") or [])[:10],
        "artifact_id": artifact.get("artifact_id") or metadata.get("artifact_id"),
        "artifact_role": artifact.get("role") or metadata.get("artifact_role"),
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def _snapshot_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    path = str(artifact.get("path") or artifact.get("output_path") or "").strip()
    payload = {
        "artifact_id": str(artifact.get("artifact_id") or ""),
        "role": str(artifact.get("role") or ""),
        "name": str(artifact.get("name") or ""),
        "kind": str(artifact.get("kind") or ""),
        "layer_id": str(artifact.get("layer_id") or ""),
        "file_name": Path(path).name if path else "",
        "path": path,
        "algorithm_id": str(artifact.get("algorithm_id") or ""),
        "source_action": str(artifact.get("source_action") or ""),
        "source_step": artifact.get("source_step"),
        "crs": str(artifact.get("crs") or ""),
        "geometry_type": str(artifact.get("geometry_type") or ""),
        "feature_count": artifact.get("feature_count"),
        "input_layer_ids": list(artifact.get("input_layer_ids") or [])[:6],
        "input_artifact_ids": list(artifact.get("input_artifact_ids") or [])[:6],
        "reusable": artifact.get("reusable"),
        "display_summary": str(artifact.get("display_summary") or ""),
    }
    return make_json_safe({key: value for key, value in payload.items() if value not in (None, "", [])})


def _snapshot_risk(item: dict[str, Any], *, source: str, action: str, step_index: Any) -> dict[str, Any]:
    risk = dict(item.get("risk") or {})
    diagnosis = dict(risk.get("diagnosis") or item.get("diagnosis") or {})
    return {
        "source": source,
        "step_index": step_index,
        "action": action,
        "code": str(item.get("code") or risk.get("code") or ""),
        "severity": str(item.get("severity") or risk.get("severity") or ""),
        "message": _truncate_text(str(item.get("message") or risk.get("message") or "")),
        "diagnosis": compact_value(diagnosis, max_depth=2) if diagnosis else {},
    }


def _artifact_relevance_score(artifact: dict[str, Any], user_request: str) -> int:
    role = str(artifact.get("role") or "").strip().lower()
    score = {"final": 7, "intermediate": 5, "input": 4, "report": 1}.get(role, 2)
    if artifact.get("reusable") is False:
        score -= 2
    if artifact.get("source_step") is not None:
        score += 1
    request_terms = _search_terms(user_request)
    artifact_text = _artifact_search_text(artifact)
    if request_terms and artifact_text:
        score += sum(2 for term in request_terms if term and term in artifact_text)
    return max(score, 0)


def _artifact_search_text(artifact: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "artifact_id",
        "role",
        "name",
        "kind",
        "layer_id",
        "path",
        "algorithm_id",
        "source_action",
        "display_title",
        "display_summary",
    ):
        values.append(str(artifact.get(key) or ""))
    for key in ("fields", "input_layer_ids", "input_artifact_ids"):
        values.extend(str(item) for item in list(artifact.get(key) or []))
    lineage = dict(artifact.get("lineage") or {})
    values.extend(str(value) for value in lineage.values() if not isinstance(value, (dict, list)))
    return _normalize_search_text(" ".join(values))


def _search_terms(text: str) -> list[str]:
    normalized = _normalize_search_text(text)
    terms = [term for term in normalized.replace("/", " ").replace("\\", " ").split() if len(term) >= 2]
    if not terms and normalized:
        terms = [normalized]
    return terms[:20]


def _normalize_search_text(text: str) -> str:
    return str(text or "").lower().replace("_", " ").replace("-", " ")


def _source_step_sort_value(artifact: dict[str, Any]) -> int:
    try:
        return int(artifact.get("source_step") or 0)
    except (TypeError, ValueError):
        return 0


def compact_value(value: Any, *, max_depth: int = 4) -> Any:
    """Generic JSON-safe compaction for action inputs and discovery payloads."""

    safe_value = make_json_safe(value)
    if max_depth <= 0:
        return _summarize_value(safe_value)
    if isinstance(safe_value, str):
        return _truncate_text(safe_value)
    if isinstance(safe_value, (int, float, bool)) or safe_value is None:
        return safe_value
    if isinstance(safe_value, list):
        return [
            compact_value(item, max_depth=max_depth - 1)
            for item in safe_value[:MAX_GENERIC_LIST_ITEMS]
        ]
    if isinstance(safe_value, dict):
        compact: dict[str, Any] = {}
        for index, (key, item) in enumerate(safe_value.items()):
            if index >= MAX_GENERIC_DICT_ITEMS:
                compact["_truncated_key_count"] = len(safe_value) - MAX_GENERIC_DICT_ITEMS
                break
            if key in _OMITTED_OBSERVATION_DATA_KEYS:
                continue
            compact[str(key)] = compact_value(item, max_depth=max_depth - 1)
        return compact
    return _truncate_text(safe_value)


def _summarize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {"_type": "object", "key_count": len(value)}
    if isinstance(value, list):
        return {"_type": "array", "item_count": len(value)}
    if isinstance(value, str):
        return _truncate_text(value)
    return value


def _truncate_text(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = str(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}... [truncated {len(text) - max_length} chars]"
