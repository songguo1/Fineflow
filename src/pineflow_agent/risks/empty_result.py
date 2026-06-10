"""Empty-result diagnosis helpers."""

from __future__ import annotations

from typing import Any


class EmptyResultDiagnoser:
    """Generate lightweight diagnostics for successful tools that produced no rows/features."""

    def diagnose(self, *, plan: Any, observation: Any, state: Any) -> dict[str, Any]:
        action = str(getattr(plan, "action", "") or "")
        action_input = dict(getattr(plan, "action_input", None) or {})
        tree = state.to_dict() if hasattr(state, "to_dict") else dict(state or {})
        cause_records: list[dict[str, Any]] = []
        suggestion_records: list[dict[str, Any]] = []

        refs = _input_refs(action_input)
        layers = [_resolve_layer(tree, ref) for ref in refs]
        layers = [layer for layer in layers if layer]
        layer_summaries = [_layer_summary(layer, requested_ref=ref) for ref, layer in zip(refs, layers)]
        output_layer = dict((dict(getattr(observation, "data", None) or {}).get("layer") or {}))
        output_summary = _layer_summary(output_layer)
        predicate = str(action_input.get("predicate") or "").strip()
        operator = str(action_input.get("operator") or "").strip()
        field = str(action_input.get("field") or "").strip()
        value = action_input.get("value")
        max_distance = _to_float(action_input.get("max_distance"))
        discard_nonmatching = bool(action_input.get("discard_nonmatching"))

        if any(_feature_count(layer) == 0 for layer in layers):
            cause_records.append(
                _cause(
                    "input_empty",
                    "One or more input layers already contain 0 features.",
                    evidence={"input_layers": [item for item in layer_summaries if item.get("feature_count") == 0]},
                )
            )
            suggestion_records.append(
                _action_option(
                    "inspect_inputs",
                    "Inspect input layers",
                    "state_query",
                    reason="At least one upstream layer is already empty.",
                )
            )
        if len(layers) >= 2 and _crs(layers[0]) and _crs(layers[1]) and _crs(layers[0]) != _crs(layers[1]):
            cause_records.append(
                _cause(
                    "crs_mismatch",
                    "Input layers use different CRS values.",
                    evidence={
                        "input_layers": [
                            {"name": item.get("name"), "crs": item.get("crs")}
                            for item in layer_summaries[:2]
                        ]
                    },
                )
            )
            suggestion_records.append(
                _action_option(
                    "reproject_inputs",
                    "Reproject inputs to one CRS",
                    "replan",
                    reason="Spatial overlay on mixed CRS can produce an empty result.",
                )
            )
        extent_relation = ""
        if action in {
            "clip_layer",
            "intersect_layer",
            "difference_layer",
            "extract_by_location",
            "join_by_location",
            "count_points_in_polygon",
        } and len(layers) >= 2:
            if not _extents_overlap(_extent(layers[0]), _extent(layers[1])):
                extent_relation = "no_overlap"
                cause_records.append(
                    _cause(
                        "extent_mismatch",
                        "Input layer extents do not appear to overlap.",
                        evidence={
                            "input_layers": [
                                {"name": item.get("name"), "extent": item.get("extent")}
                                for item in layer_summaries[:2]
                            ]
                        },
                    )
                )
                suggestion_records.append(
                    _action_option(
                        "inspect_extents",
                        "Inspect layer extents",
                        "state_query",
                        reason="The two spatial inputs may not cover the same area.",
                        )
                    )
        if action in {"extract_by_location", "join_by_location"} and predicate:
            cause_records.append(
                _cause(
                    "spatial_predicate_no_match",
                    "The chosen spatial predicate may not match how the input layers relate.",
                    evidence={
                        "predicate": predicate,
                        "input_layers": [
                            {
                                "name": item.get("name"),
                                "geometry_type": item.get("geometry_type"),
                                "feature_count": item.get("feature_count"),
                            }
                            for item in layer_summaries[:2]
                        ],
                    },
                )
            )
            suggestion_records.append(
                _action_option(
                    "change_spatial_relation",
                    "Change the spatial predicate",
                    "replan",
                    reason="The current spatial relation may be too strict for these two layers.",
                )
            )
        if action == "join_by_location" and discard_nonmatching:
            cause_records.append(
                _cause(
                    "nonmatching_rows_dropped",
                    "Unmatched input features were discarded, and no spatial matches were found.",
                    evidence={"discard_nonmatching": True, "predicate": predicate},
                )
            )
            suggestion_records.append(
                _action_option(
                    "keep_nonmatching_features",
                    "Keep unmatched input features",
                    "replan",
                    reason="Disabling discard_nonmatching keeps the input rows even when no join target matches.",
                )
            )
        if action == "join_by_nearest":
            if max_distance is not None:
                cause_records.append(
                    _cause(
                        "nearest_distance_limit",
                        "The nearest-join search distance may be too small to find any candidate feature.",
                        evidence={"max_distance": max_distance},
                    )
                )
                suggestion_records.append(
                    _action_option(
                        "increase_search_distance",
                        "Increase the nearest-search distance",
                        "replan",
                        reason="A larger search radius may allow the join to find candidates.",
                    )
                )
            if discard_nonmatching:
                cause_records.append(
                    _cause(
                        "nonmatching_rows_dropped",
                        "Unmatched input features were discarded, and no nearest feature was accepted.",
                        evidence={"discard_nonmatching": True, "max_distance": max_distance},
                    )
                )
                suggestion_records.append(
                    _action_option(
                        "keep_nonmatching_features",
                        "Keep unmatched input features",
                        "replan",
                        reason="Disabling discard_nonmatching keeps rows even when the nearest join finds no match.",
                    )
                )
        if action == "extract_by_attribute":
            if field or value not in (None, ""):
                cause_records.append(
                    _cause(
                        "filter_no_match",
                        "The attribute filter may not match any records.",
                        evidence={"field": field, "operator": operator, "value": value},
                    )
                )
                suggestion_records.append(
                    _action_option(
                        "modify_filter",
                        "Modify the filter condition",
                        "replan",
                        reason="The current attribute filter may be too strict.",
                    )
                )
                suggestion_records.append(
                    _action_option(
                        "inspect_fields",
                        "Inspect field values",
                        "state_query",
                        reason="Seeing available values helps choose a filter that matches records.",
                    )
                )
        metadata = dict(output_layer.get("metadata") or {})
        if str(output_layer.get("kind") or "") == "raster":
            if not metadata.get("band_count"):
                cause_records.append(
                    _cause(
                        "raster_band_missing",
                        "Raster band metadata is missing.",
                        evidence={"layer_name": str(output_layer.get("name") or output_layer.get("layer_id") or "")},
                    )
                )
            if not metadata.get("extent"):
                cause_records.append(
                    _cause(
                        "raster_extent_missing",
                        "Raster extent metadata is missing.",
                        evidence={"layer_name": str(output_layer.get("name") or output_layer.get("layer_id") or "")},
                    )
                )
            suggestion_records.append(
                _action_option(
                    "inspect_raster_settings",
                    "Inspect raster settings",
                    "state_query",
                    reason="Band, extent, NoData, or resolution metadata may explain the empty result.",
                )
            )

        if not cause_records:
            cause_records.append(
                _cause(
                    "unknown_empty_result",
                    "The tool ran successfully, but no output records were produced.",
                    evidence={"action": action},
                )
            )
        suggestion_records.extend(_baseline_actions(action, cause_records))
        suggestion_records = _dedupe_actions(suggestion_records)
        causes = [str(item.get("message") or "") for item in cause_records if str(item.get("message") or "").strip()]
        suggestions = [str(item.get("label") or "") for item in suggestion_records if str(item.get("label") or "").strip()]
        if not suggestions:
            suggestions.append("Review CRS, spatial predicates, filters, and input data coverage.")
        return {
            "contract_version": 2,
            "action": action,
            "empty_output_kind": _empty_output_kind(output_layer),
            "input_layers": [str(item.get("name") or "") for item in layer_summaries if str(item.get("name") or "").strip()],
            "input_layer_records": layer_summaries,
            "output_layer": str(output_summary.get("name") or ""),
            "output_layer_record": output_summary,
            "predicate": predicate,
            "field": field,
            "operator": operator,
            "value": value,
            "max_distance": max_distance,
            "discard_nonmatching": discard_nonmatching,
            "extent_relation": extent_relation,
            "possible_causes": causes,
            "possible_cause_codes": [str(item.get("code") or "") for item in cause_records if str(item.get("code") or "").strip()],
            "possible_cause_records": cause_records,
            "suggested_next_actions": suggestions,
            "suggested_actions": suggestions,
            "suggested_action_options": suggestion_records,
        }


def _input_refs(action_input: dict[str, Any]) -> list[str]:
    refs = []
    for key, value in action_input.items():
        if key.endswith("_ref") and str(value or "").strip():
            refs.append(str(value))
    return refs


def _resolve_layer(tree: dict[str, Any], ref: str) -> dict[str, Any]:
    aliases = dict(tree.get("aliases") or {})
    target = aliases.get(ref, ref)
    for layer in list(tree.get("layers") or []):
        if not isinstance(layer, dict):
            continue
        if target in {layer.get("layer_id"), layer.get("name"), layer.get("source")}:
            return dict(layer)
    return {}


def _feature_count(layer: dict[str, Any]) -> int | None:
    value = dict(layer.get("metadata") or {}).get("feature_count")
    return value if isinstance(value, int) else None


def _crs(layer: dict[str, Any]) -> str:
    return str(dict(layer.get("metadata") or {}).get("crs") or "")


def _extent(layer: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(layer.get("metadata") or {}).get("extent") or {})


def _extents_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a or not b:
        return True
    try:
        ax1, ay1, ax2, ay2 = float(a["xmin"]), float(a["ymin"]), float(a["xmax"]), float(a["ymax"])
        bx1, by1, bx2, by2 = float(b["xmin"]), float(b["ymin"]), float(b["xmax"]), float(b["ymax"])
    except (KeyError, TypeError, ValueError):
        return True
    return ax1 <= bx2 and ax2 >= bx1 and ay1 <= by2 and ay2 >= by1


def _cause(code: str, message: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "evidence": dict(evidence or {})}


def _action_option(key: str, label: str, intent: str, *, reason: str = "") -> dict[str, str]:
    payload = {"key": key, "label": label, "intent": intent}
    if reason:
        payload["reason"] = reason
    return payload


def _baseline_actions(action: str, causes: list[dict[str, Any]]) -> list[dict[str, str]]:
    cause_codes = {str(item.get("code") or "") for item in causes}
    actions: list[dict[str, str]] = [
        _action_option("keep_empty_result", "Keep the empty result", "accept_result"),
    ]
    if "filter_no_match" in cause_codes or action == "extract_by_attribute":
        actions.append(_action_option("modify_filter", "Modify the filter condition", "replan"))
        actions.append(_action_option("inspect_fields", "Inspect field values", "state_query"))
    if "crs_mismatch" in cause_codes:
        actions.append(_action_option("check_crs", "Check layer CRS", "state_query"))
        actions.append(_action_option("reproject_inputs", "Reproject inputs to one CRS", "replan"))
    if "extent_mismatch" in cause_codes:
        actions.append(_action_option("inspect_extents", "Inspect layer extents", "state_query"))
    if "input_empty" in cause_codes:
        actions.append(_action_option("inspect_inputs", "Inspect input layers", "state_query"))
    if action in {"clip_layer", "intersect_layer", "difference_layer", "extract_by_location"}:
        actions.append(_action_option("change_spatial_relation", "Change the spatial predicate or overlay layer", "replan"))
    actions.append(_action_option("backtrack_previous_step", "Go back to the previous step", "replan"))
    return actions


def _dedupe_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for action in actions:
        key = str(action.get("key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result


def _layer_summary(layer: dict[str, Any], *, requested_ref: str = "") -> dict[str, Any]:
    metadata = dict(layer.get("metadata") or {})
    return {
        "requested_ref": requested_ref,
        "layer_id": str(layer.get("layer_id") or ""),
        "name": str(layer.get("name") or layer.get("layer_id") or requested_ref or ""),
        "kind": str(layer.get("kind") or ""),
        "source": str(layer.get("source") or ""),
        "crs": str(metadata.get("crs") or ""),
        "geometry_type": str(metadata.get("geometry_type") or ""),
        "feature_count": metadata.get("feature_count", metadata.get("row_count")),
        "extent": dict(metadata.get("extent") or {}),
    }


def _empty_output_kind(layer: dict[str, Any]) -> str:
    kind = str(layer.get("kind") or "").strip()
    return kind or "unknown"


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
