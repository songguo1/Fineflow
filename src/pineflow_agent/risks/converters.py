"""Converters from legacy issues/warnings into GISRisk objects."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from pineflow_agent.core.field_metadata import field_records
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.policies.crs_recommendation import crs_recommendation_from_params
from pineflow_agent.risks.models import GISRisk
from pineflow_agent.risks.taxonomy import category_for_code


def risks_from_issues(
    issues: list[Any] | tuple[Any, ...],
    *,
    tool_name: str = "",
    state_tree: Any = None,
) -> list[GISRisk]:
    return [
        risk_from_issue(issue, tool_name=tool_name, state_tree=state_tree)
        for issue in list(issues or [])
        if issue is not None
    ]


def risk_from_issue(issue: Any, *, tool_name: str = "", state_tree: Any = None) -> GISRisk:
    code = str(getattr(issue, "code", "") or "")
    stage = str(getattr(issue, "stage", "") or "")
    severity = str(getattr(issue, "severity", "warning") or "warning")
    params = dict(getattr(issue, "params", None) or {})
    repair = getattr(issue, "repair", None)
    repair_action = _repair_action_dict(repair)
    message = str(getattr(issue, "message", "") or code or "GIS risk")
    choices = _suggested_choices(code, params, state_tree)
    return GISRisk(
        code=code,
        category=category_for_code(code, stage),
        severity="error" if severity == "error" else "info" if severity == "info" else "warning",
        stage=stage,
        message=message,
        technical_detail=message,
        tool_name=tool_name,
        layer_refs=_layer_refs(params),
        confirmation_required=bool(getattr(repair, "requires_confirmation", False)),
        blocking=severity == "error",
        auto_repair_available=bool(repair_action),
        repair_action=repair_action,
        suggested_choices=choices,
        diagnosis=_diagnosis_for_code(
            code,
            params,
            tool_name=tool_name,
            state_tree=state_tree,
            suggested_choices=choices,
        ),
        affects_result_trust=stage == "preflight" or code.startswith("empty_"),
    )


def risk_from_warning(warning: dict[str, Any], *, tool_name: str = "") -> GISRisk:
    code = str(warning.get("code") or "postflight_warning")
    stage = str(warning.get("stage") or "postflight")
    diagnosis = _diagnosis_for_warning(code, warning)
    return GISRisk(
        code=code,
        category=str(warning.get("category") or category_for_code(code, stage)),
        severity=str(warning.get("severity") or "warning"),
        stage=stage,
        message=str(warning.get("message") or code),
        technical_detail=str(warning.get("technical_detail") or warning.get("message") or ""),
        tool_name=tool_name,
        layer_refs=_layer_refs(warning),
        confirmation_required=bool(warning.get("confirmation_required", False)),
        blocking=bool(warning.get("blocking", False)),
        auto_repair_available=bool(warning.get("auto_repair_available", False)),
        repair_action=dict(warning.get("repair_action") or {}),
        suggested_choices=[dict(item) for item in list(warning.get("suggested_choices") or []) if isinstance(item, dict)],
        diagnosis=diagnosis,
        affects_result_trust=bool(warning.get("affects_result_trust", True)),
    )


def warning_from_risk(risk: GISRisk) -> dict[str, Any]:
    payload = risk.to_dict()
    payload["risk"] = risk.to_dict()
    return payload


def _repair_action_dict(repair: Any) -> dict[str, Any]:
    if repair is None:
        return {}
    action = getattr(repair, "action", None)
    if isinstance(action, dict) and action:
        return dict(action)
    steps = getattr(repair, "steps", None)
    if isinstance(steps, list) and steps and isinstance(steps[0], dict):
        return dict(steps[0])
    return {}


def _layer_refs(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("layer", "layers", "input_layer", "overlay_layer", "raster_refs", "mask_ref"):
        value = payload.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if str(item or "").strip())
        elif isinstance(value, dict):
            label = str(value.get("layer_id") or value.get("name") or value.get("source") or "").strip()
            if label:
                refs.append(label)
        elif str(value or "").strip():
            refs.append(str(value))
    return list(dict.fromkeys(refs))


def _suggested_choices(code: str, params: dict[str, Any], state_tree: Any) -> list[dict[str, Any]]:
    if code == "unknown_field":
        missing = [str(item) for item in list(params.get("fields") or []) if str(item or "").strip()]
        layer_name = str(params.get("layer") or "")
        return _field_choices(missing[0] if missing else "", layer_name=layer_name, state_tree=state_tree, params=params)
    if code == "unknown_layer":
        target = str(params.get("layer") or "")
        return _layer_choices(target, state_tree)
    return []


def _diagnosis_for_code(
    code: str,
    params: dict[str, Any] | None = None,
    *,
    tool_name: str = "",
    state_tree: Any = None,
    suggested_choices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(params or {})
    diagnosis: dict[str, Any] = {}
    crs_recommendation = crs_recommendation_from_params(payload)
    if crs_recommendation:
        diagnosis["crs_recommendation"] = crs_recommendation
    disambiguation = _disambiguation_for_code(code, payload, state_tree=state_tree, suggested_choices=suggested_choices or [])
    if disambiguation:
        diagnosis["disambiguation"] = disambiguation
    raster = _raster_diagnosis_for_code(code, payload)
    if raster:
        diagnosis["raster_analysis"] = raster
        for key, value in raster.items():
            if key in {"possible_causes", "suggested_actions", "suggested_action_options"}:
                if value and not diagnosis.get(key):
                    diagnosis[key] = value
            elif value not in ({}, [], "", None) and key not in diagnosis:
                diagnosis[key] = value
    skills = _suggested_skills_for_code(code, tool_name=tool_name)
    if skills:
        diagnosis["suggested_skills"] = skills
    return diagnosis


def _diagnosis_for_warning(code: str, warning: dict[str, Any]) -> dict[str, Any]:
    diagnosis = make_json_safe(dict(warning.get("diagnosis") or {}))
    normalized = _diagnosis_for_code(code, warning, suggested_choices=list(warning.get("suggested_choices") or []))
    for key, value in normalized.items():
        if key in {"possible_causes", "suggested_actions", "suggested_action_options"}:
            if value and not diagnosis.get(key):
                diagnosis[key] = value
            continue
        if value not in ({}, [], "", None) and key not in diagnosis:
            diagnosis[key] = value
    return make_json_safe(diagnosis)


def _suggested_skills_for_code(code: str, *, tool_name: str = "") -> list[str]:
    normalized = str(code or "").strip()
    action = str(tool_name or "").strip()
    if normalized in {"distance_requires_projected_crs", "overlay_crs_mismatch", "unknown_crs", "raster_crs_mismatch"}:
        skills = ["crs_selection"]
        if action in {"join_by_location", "join_by_nearest", "count_points_in_polygon", "extract_by_location"}:
            skills.append("spatial_join")
        return skills
    if normalized == "unknown_field":
        if action in {"field_calculator"}:
            return ["field_calculator"]
        if action in {"join_by_location", "join_by_nearest", "count_points_in_polygon", "extract_by_location"}:
            return ["spatial_join"]
    if normalized == "spatial_predicate_geometry_mismatch":
        return ["spatial_join"]
    if normalized in {
        "raster_extent_no_overlap",
        "raster_extent_partial_overlap",
        "raster_pixel_size_mismatch",
        "raster_nodata_propagation",
        "raster_resampling_recommendation",
    }:
        return ["raster_basics"]
    if normalized in {"raster_slope_output", "raster_hillshade_output", "contour_empty_output"}:
        return ["dem_analysis", "raster_basics"]
    return []


def _field_choices(target: str, *, layer_name: str, state_tree: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    field_details = _field_candidates(layer_name, state_tree=state_tree, params=params)
    ranked_names = set(_rank_strings(target, [str(item.get("name") or "") for item in field_details])[:5])
    choices: list[dict[str, Any]] = []
    for item in field_details:
        name = str(item.get("name") or "")
        if not name or name not in ranked_names:
            continue
        choices.append(
            {
                "value": name,
                "label": name,
                "field": name,
                "type": str(item.get("type") or "unknown"),
                "sample": list(item.get("sample_values") or item.get("sample") or []),
                "null_count": item.get("null_count"),
            }
        )
    return choices


def _layer_choices(target: str, state_tree: Any) -> list[dict[str, Any]]:
    tree = state_tree.to_dict() if hasattr(state_tree, "to_dict") else dict(state_tree or {})
    layers = [dict(item) for item in list(tree.get("layers") or []) if isinstance(item, dict)]
    names = [str(layer.get("name") or layer.get("layer_id") or "") for layer in layers]
    ranked_names = set(_rank_strings(target, names)[:5])
    choices: list[dict[str, Any]] = []
    for layer in layers:
        name = str(layer.get("name") or layer.get("layer_id") or "")
        if name not in ranked_names:
            continue
        metadata = dict(layer.get("metadata") or {})
        choices.append(
            {
                "value": str(layer.get("layer_id") or name),
                "label": name,
                "layer_id": str(layer.get("layer_id") or ""),
                "kind": str(layer.get("kind") or ""),
                "crs": str(metadata.get("crs") or ""),
                "geometry_type": str(metadata.get("geometry_type") or ""),
                "feature_count": metadata.get("feature_count"),
                "extent": metadata.get("extent") or {},
            }
        )
    return choices


def _disambiguation_for_code(
    code: str,
    params: dict[str, Any],
    *,
    state_tree: Any,
    suggested_choices: list[dict[str, Any]],
) -> dict[str, Any]:
    if code == "unknown_field":
        missing = [str(item) for item in list(params.get("fields") or []) if str(item or "").strip()]
        target = missing[0] if missing else ""
        return {
            "kind": "field",
            "target": target,
            "layer": str(params.get("layer") or ""),
            "candidate_count": len(suggested_choices),
            "candidates": make_json_safe(list(suggested_choices)),
        } if target or suggested_choices else {}
    if code == "unknown_layer":
        return {
            "kind": "layer",
            "target": str(params.get("layer") or ""),
            "candidate_count": len(suggested_choices),
            "candidates": make_json_safe(list(suggested_choices)),
        } if str(params.get("layer") or "").strip() or suggested_choices else {}
    return {}


def _raster_diagnosis_for_code(code: str, params: dict[str, Any]) -> dict[str, Any]:
    normalized = str(code or "").strip()
    if normalized not in {
        "raster_extent_no_overlap",
        "raster_extent_partial_overlap",
        "raster_pixel_size_mismatch",
        "raster_nodata_propagation",
        "raster_resampling_recommendation",
        "raster_slope_output",
        "raster_hillshade_output",
        "contour_empty_output",
    }:
        return {}

    inputs = _raster_input_layers(params)
    output_layer = _raster_output_layer(params)
    diagnosis: dict[str, Any] = {
        "risk_kind": "raster_analysis",
        "input_layers": inputs,
    }
    if output_layer:
        diagnosis["output_layer"] = output_layer

    if normalized == "raster_extent_no_overlap":
        diagnosis.update(
            {
                "extent_relation": "no_overlap",
                "possible_causes": [
                    "输入栅格空间范围不相交。",
                    "输入数据虽然坐标系名称一致，但实际覆盖区域不同。",
                ],
                "suggested_actions": [
                    "检查两个栅格的 extent 是否覆盖同一研究区。",
                    "必要时先裁剪或重投影到同一范围后再计算。",
                ],
            }
        )
    elif normalized == "raster_extent_partial_overlap":
        diagnosis.update(
            {
                "extent_relation": "partial_overlap",
                "possible_causes": [
                    "多个栅格只在部分区域重叠。",
                    "输出时共享区域外的像元可能被写成 NoData。",
                ],
                "suggested_actions": [
                    "确认分析是否只需要共享范围。",
                    "需要完整覆盖时先统一 extent 或先裁剪到公共范围。",
                ],
            }
        )
    elif normalized == "raster_pixel_size_mismatch":
        diagnosis.update(
            {
                "pixel_size_a": _float_pair(params.get("pixel_size_a")),
                "pixel_size_b": _float_pair(params.get("pixel_size_b")),
                "possible_causes": [
                    "输入栅格分辨率不同，运行时会发生重采样。",
                ],
                "suggested_actions": [
                    "确认哪个栅格应该作为目标分辨率。",
                    "必要时先统一像元大小，再做 raster calculator 或叠加分析。",
                ],
            }
        )
    elif normalized == "raster_nodata_propagation":
        diagnosis.update(
            {
                "nodata": _normalize_nodata(params.get("nodata")),
                "possible_causes": [
                    "输入栅格存在 NoData 像元，计算或采样时会把空值传播到结果中。",
                ],
                "suggested_actions": [
                    "检查 NoData 是否落在研究区内。",
                    "必要时先填补 NoData，或在表达式里显式处理空值。",
                ],
            }
        )
    elif normalized == "raster_resampling_recommendation":
        diagnosis.update(
            {
                "layer": str(params.get("layer") or ""),
                "data_type": str(params.get("data_type") or ""),
                "recommended_resampling": _resampling_record(params.get("recommended_resampling")),
                "possible_causes": [
                    "重投影时如果采样方法不合适，连续值会被离散化，离散分类会被平滑。",
                ],
                "suggested_actions": [
                    "连续型栅格优先用 bilinear/cubic，分类栅格优先用 nearest。",
                ],
            }
        )
    elif normalized == "raster_slope_output":
        diagnosis.update(
            {
                "output_kind": "slope",
                "expected_value_range": "0-90",
                "recommended_checks": ["检查坡度是否超出 0-90 度", "检查 DEM NoData 和边缘异常值"],
                "possible_causes": [
                    "DEM 边缘或 NoData 区域可能产生异常坡度值。",
                ],
                "suggested_actions": [
                    "抽样检查结果范围，确认是否出现明显异常值。",
                ],
            }
        )
    elif normalized == "raster_hillshade_output":
        diagnosis.update(
            {
                "output_kind": "hillshade",
                "recommended_checks": ["检查结果是否整体发黑", "确认 Z_FACTOR 和 SCALE 是否与高程单位匹配"],
                "possible_causes": [
                    "高程单位与水平单位不一致时，阴影结果容易失真。",
                ],
                "suggested_actions": [
                    "必要时调整 Z_FACTOR 或 SCALE 后重新生成 hillshade。",
                ],
            }
        )
    elif normalized == "contour_empty_output":
        diagnosis.update(
            {
                "output_kind": "contour",
                "possible_causes": [
                    "等高距大于 DEM 高程变化范围。",
                    "输入栅格无有效高程值或高程范围过窄。",
                ],
                "suggested_actions": [
                    "减小 contour interval 后重新生成。",
                    "先检查 DEM 的最小值、最大值和 NoData 范围。",
                ],
            }
        )
    return make_json_safe({key: value for key, value in diagnosis.items() if value not in ({}, [], "", None)})


def _raster_input_layers(params: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("layers", "raster_refs", "input_layers"):
        value = params.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if str(item or "").strip())
    for key in ("layer", "input_ref", "raster_ref", "mask_ref"):
        value = params.get(key)
        if isinstance(value, dict):
            text = str(value.get("name") or value.get("layer_id") or value.get("source") or "").strip()
        else:
            text = str(value or "").strip()
        if text:
            values.append(text)
    return list(dict.fromkeys(values))


def _raster_output_layer(params: dict[str, Any]) -> str:
    for key in ("layer", "output_layer", "artifact"):
        value = params.get(key)
        if isinstance(value, dict):
            text = str(value.get("name") or value.get("layer_id") or value.get("source") or "").strip()
            if text:
                return text
    return ""


def _float_pair(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)):
        result: list[float] = []
        for item in list(value)[:2]:
            try:
                result.append(float(item))
            except (TypeError, ValueError):
                return []
        return result if result else []
    return []


def _resampling_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    record = {
        "method": str(value.get("method") or ""),
        "value": value.get("value"),
        "data_semantics": str(value.get("data_semantics") or ""),
    }
    return {key: item for key, item in record.items() if item not in ("", None)}


def _normalize_nodata(value: Any) -> Any:
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def _field_candidates(layer_name: str, *, state_tree: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    tree = state_tree.to_dict() if hasattr(state_tree, "to_dict") else dict(state_tree or {})
    target_layer = _find_layer_by_name(tree, layer_name)
    metadata = dict(target_layer.get("metadata") or {}) if target_layer else {}
    if not metadata and params.get("available_fields"):
        metadata = {"fields": list(params.get("available_fields") or [])}
    return [
        {
            **record,
            "type": str(record.get("type") or "unknown"),
            "sample_values": make_json_safe(list(record.get("sample_values") or [])),
        }
        for record in field_records(metadata)
    ]


def _find_layer_by_name(tree: dict[str, Any], layer_name: str) -> dict[str, Any]:
    needle = str(layer_name or "").strip()
    if not needle:
        return {}
    for layer in list(tree.get("layers") or []):
        if not isinstance(layer, dict):
            continue
        if needle in {str(layer.get("name") or ""), str(layer.get("layer_id") or ""), str(layer.get("source") or "")}:
            return dict(layer)
    return {}


def _rank_strings(target: str, values: list[str]) -> list[str]:
    needle = str(target or "").lower()
    scored = []
    for value in values:
        text = str(value or "")
        lower = text.lower()
        score = SequenceMatcher(None, needle, lower).ratio()
        if needle and needle in lower:
            score += 0.5
        scored.append((score, text))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for score, text in scored if text and (score > 0.25 or not needle)]
