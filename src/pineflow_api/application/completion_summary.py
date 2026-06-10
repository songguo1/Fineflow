"""Structured completion-summary helpers for finished GIS runs."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action

GENERIC_COMPLETION_MESSAGES = {
    "",
    "task completed.",
    "任务完成。",
    "处理完成。",
    "resumed pending gis task completed.",
    "confirmed repair completed and the original gis action finished.",
    "task completed after repair.",
}

SUMMARY_ACTION_EXCLUDES = {
    "select_toolkit",
    "load_skill",
    "suggest_skill",
    "inspect_workspace",
    "discover_algorithms",
    "algorithm_help",
    "run_algorithm",
    "final_answer",
}


def apply_completion_summary(payload: dict[str, Any]) -> dict[str, Any]:
    result = make_json_safe(dict(payload or {}))
    if str(result.get("status") or "").strip().lower() != "completed":
        return result
    summary = build_completion_summary(result)
    if not summary:
        return result
    result["completion_summary"] = summary
    result["completion_delivery"] = build_completion_delivery(result, summary=summary)
    final_message = str(result.get("final_message") or "").strip()
    if _should_replace_final_message(final_message):
        result["final_message"] = summary
    return result


def build_completion_summary(payload: dict[str, Any]) -> str:
    outputs = [dict(item) for item in list(payload.get("outputs") or []) if isinstance(item, dict)]
    final_output = _pick_final_output(outputs)
    if not final_output:
        return ""

    lead = _lead_sentence(final_output)
    if not lead:
        return ""

    report_audit = dict(payload.get("report_audit") or {})
    steps = _step_titles(report_audit)
    source_note = _source_resume_sentence(report_audit)
    risk_count = _nonblocking_notice_count(payload)
    parts = [lead]
    if source_note:
        parts.append(source_note)
    if steps:
        parts.append(f"主要步骤：{'、'.join(steps)}。")
    if risk_count > 0:
        parts.append(f"另有 {risk_count} 条提示可在工作流中查看。")
    return " ".join(part for part in parts if part)


def build_completion_delivery(payload: dict[str, Any], *, summary: str = "") -> dict[str, Any]:
    outputs = [dict(item) for item in list(payload.get("outputs") or []) if isinstance(item, dict)]
    report_audit = dict(payload.get("report_audit") or {})
    final_output = _pick_final_output(outputs)
    goal = str(dict(payload.get("goal_contract") or {}).get("goal") or "").strip()
    steps = _process_steps(report_audit)
    metrics = _completion_metrics(report_audit, final_output, goal=goal)
    return make_json_safe(
        {
            "title": "处理完成",
            "message": summary or build_completion_summary(payload),
            "run_start_summary": _run_start_summary(goal, steps, report_audit=report_audit),
            "output": _output_delivery(final_output),
            "metrics": metrics,
            "process": steps,
            "process_text": " → ".join(item["title"] for item in steps if item.get("title")),
        }
    )


def _should_replace_final_message(final_message: str) -> bool:
    normalized = str(final_message or "").strip().lower()
    return normalized in GENERIC_COMPLETION_MESSAGES


def _pick_final_output(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    finals = [item for item in outputs if _is_final_output(item)]
    if finals:
        return finals[0]
    return outputs[0] if outputs else {}


def _lead_sentence(output: dict[str, Any]) -> str:
    summary = str(output.get("display_summary") or "").strip()
    if summary:
        return summary
    name = str(output.get("name") or output.get("layer_id") or output.get("artifact_id") or "结果").strip()
    path = str(output.get("path") or "").strip()
    count_text = _count_text(output)
    geometry = str(output.get("geometry_type") or "").strip()
    crs = str(output.get("crs") or "").strip()
    detail_parts = [part for part in (count_text, geometry, crs) if part]
    detail = f"（{'，'.join(detail_parts)}）" if detail_parts else ""
    if str(output.get("algorithm_id") or "").strip().lower() == "export_result" and path:
        return f"已导出 {name}{detail} 到 {Path(path).name}。"
    return f"生成 {name}{detail}。"


def _count_text(output: dict[str, Any]) -> str:
    count = output.get("feature_count")
    if count is None:
        count = output.get("row_count")
    if count is None:
        return ""
    unit = "行" if str(output.get("kind") or "").strip().lower() == "table" else "要素"
    return f"{count} {unit}"


def _step_titles(report_audit: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for item in list(report_audit.get("executed_tools") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip().lower() == "failed":
            continue
        action = str(item.get("action") or "").strip()
        if not action or action in SUMMARY_ACTION_EXCLUDES:
            continue
        title = display_title_for_action(action)
        if title:
            titles.append(title)
    unique = list(dict.fromkeys(titles))
    if len(unique) <= 4:
        return unique
    return unique[:4] + ["导出结果" if "导出结果" in unique[4:] else "等"]


def _process_steps(report_audit: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for item in list(report_audit.get("executed_tools") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip().lower() == "failed":
            continue
        action = str(item.get("action") or "").strip()
        if not action or action in SUMMARY_ACTION_EXCLUDES:
            continue
        title = display_title_for_action(action)
        if not title:
            continue
        steps.append(
            {
                "action": action,
                "title": title,
                "step_index": _int(item.get("step_index")),
            }
        )
    return _dedupe_steps(steps)


def _completion_metrics(report_audit: dict[str, Any], final_output: dict[str, Any], *, goal: str = "") -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for source in list(report_audit.get("source_loads") or []):
        if not isinstance(source, dict):
            continue
        artifact = dict(source.get("artifact") or {})
        metric = _count_metric(
            artifact or source,
            label=_source_metric_label(source, artifact, goal=goal),
            action=str(source.get("action") or ""),
            step_index=_int(source.get("step_index")),
        )
        if metric:
            metrics.append(metric)
    for item in list(report_audit.get("executed_tools") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip().lower() == "failed":
            continue
        action = str(item.get("action") or "").strip()
        if not action or action in SUMMARY_ACTION_EXCLUDES:
            continue
        output = _tool_output_record(item)
        metric = _count_metric(
            output,
            label=_tool_metric_label(action, output, item, goal=goal),
            action=action,
            step_index=_int(item.get("step_index")),
        )
        if metric:
            metrics.append(metric)
    final_metric = _count_metric(final_output, label="最终结果", action=str(final_output.get("algorithm_id") or ""), step_index=_int(final_output.get("source_step")))
    if final_metric:
        metrics.append(final_metric)
    return _dedupe_metrics(metrics)


def _run_start_summary(goal: str, steps: list[dict[str, Any]], *, report_audit: dict[str, Any] | None = None) -> list[str]:
    structured = _structured_start_summary(dict(report_audit or {}))
    if structured:
        return structured
    request = str(goal or "").strip()
    if request:
        semantic = _semantic_start_summary(request)
        if semantic:
            return semantic
    titles = [str(item.get("title") or "").strip() for item in steps if str(item.get("title") or "").strip()]
    return list(dict.fromkeys(titles))[:6]


def _structured_start_summary(report_audit: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for source in list(report_audit.get("source_loads") or []):
        if not isinstance(source, dict):
            continue
        label = _source_start_label(source)
        if label:
            items.append(label)
    for tool in list(report_audit.get("executed_tools") or []):
        if not isinstance(tool, dict):
            continue
        if str(tool.get("status") or "").strip().lower() == "failed":
            continue
        label = _tool_start_label(tool)
        if label:
            items.append(label)
    return list(dict.fromkeys(item for item in items if item))[:6]


def _semantic_start_summary(request: str) -> list[str]:
    lowered = request.lower()
    items: list[str] = []
    if _contains_any(request, ["csv", "表格"]):
        items.append(_with_target("读取", _target_name(request, ["csv", "表格"], fallback="CSV")))
        if _contains_any(request, ["点", "经纬度", "坐标"]):
            items.append("生成点图层")
    if _contains_any(request, ["河流", "水系"]):
        distance = _distance_phrase(request)
        items.append(f"构建河流 {distance}范围" if distance else "构建河流范围")
    elif _contains_any(request, ["缓冲", "buffer"]):
        distance = _distance_phrase(request)
        items.append(f"构建{distance}缓冲范围" if distance else "构建缓冲范围")
    if _contains_any(request, ["边界", "市界", "行政区", "范围内", "以内", "within"]):
        boundary = _target_name(request, ["边界", "市界", "行政区"], fallback="边界")
        items.append(f"按{boundary}筛选")
    if _contains_any(request, ["导出", "输出", "保存", "export", "save"]):
        items.append("导出结果")
    return list(dict.fromkeys(items))[:6]


def _source_start_label(source: dict[str, Any]) -> str:
    artifact = dict(source.get("artifact") or {})
    alias = str(source.get("alias") or artifact.get("name") or "").strip()
    source_type = str(source.get("source_type") or source.get("type") or artifact.get("kind") or "").strip().lower()
    if not alias:
        return ""
    if source_type in {"csv", "table"}:
        return f"读取{alias}"
    if source_type == "raster":
        return f"加载栅格 {alias}"
    return f"加载{alias}"


def _source_metric_label(source: dict[str, Any], artifact: dict[str, Any], *, goal: str) -> str:
    if str(artifact.get("row_count") or source.get("row_count") or "").strip():
        return "输入记录"
    alias = str(source.get("alias") or artifact.get("name") or "").strip()
    if alias:
        return alias
    return "输入数据"


def _tool_metric_label(action: str, output: dict[str, Any], item: dict[str, Any], *, goal: str) -> str:
    structured_label = _artifact_metric_label(action, output, item)
    if structured_label:
        return structured_label
    if action == "csv_to_points":
        return "转点后"
    if action == "buffer_layer":
        return _buffer_metric_label(output, item)
    if action == "extract_by_location":
        local_text = _metric_text_blob(output, item)
        if _contains_any(local_text, ["河流", "水系", "river", "waterway"]):
            distance = _distance_phrase(local_text) or _distance_phrase(goal)
            return f"河流 {distance}内" if distance else "河流范围内"
        if _contains_any(local_text, ["南京市", "市界", "边界", "boundary"]):
            return "边界内"
        text = _metric_text_blob(output, item, goal)
        if _contains_any(text, ["河流", "水系", "river", "waterway"]):
            distance = _distance_phrase(text)
            return f"河流 {distance}内" if distance else "河流范围内"
        if _contains_any(text, ["南京市", "市界", "边界", "boundary"]):
            return "边界内"
        return "位置筛选后"
    return display_title_for_action(action)


def _tool_start_label(item: dict[str, Any]) -> str:
    action = str(item.get("action") or "").strip()
    output = _tool_output_record(item)
    if action == "csv_to_points":
        return "生成点图层"
    if action == "buffer_layer":
        return _buffer_start_label(output, item)
    if action == "extract_by_location":
        return _extract_location_start_label(output, item)
    if action == "export_result":
        return "导出结果"
    return ""


def _artifact_metric_label(action: str, output: dict[str, Any], item: dict[str, Any]) -> str:
    if action == "csv_to_points":
        return "转点后"
    if action == "buffer_layer":
        return _buffer_metric_label(output, item)
    if action != "extract_by_location":
        return ""
    overlay = _location_overlay_artifact(output, item)
    if not overlay:
        return ""
    label = _overlay_scope_label(overlay)
    if label:
        return label
    return ""


def _buffer_metric_label(output: dict[str, Any], item: dict[str, Any]) -> str:
    base = _primary_input_name(output, item)
    distance = _tool_distance_text(output, item)
    if base and distance:
        return f"{base} {distance}范围"
    if base:
        return f"{base}缓冲范围"
    if distance:
        return f"{distance}缓冲范围"
    return "缓冲范围"


def _buffer_start_label(output: dict[str, Any], item: dict[str, Any]) -> str:
    base = _primary_input_name(output, item)
    distance = _tool_distance_text(output, item)
    if base and distance:
        return f"构建{base} {distance}范围"
    if base:
        return f"构建{base}范围"
    if distance:
        return f"构建{distance}缓冲范围"
    return "构建缓冲范围"


def _extract_location_start_label(output: dict[str, Any], item: dict[str, Any]) -> str:
    overlay = _location_overlay_artifact(output, item)
    if not overlay:
        return ""
    source_action = str(overlay.get("source_action") or overlay.get("algorithm_id") or "").strip().lower()
    if source_action in {"buffer_layer", "native:buffer"}:
        return ""
    if not _contains_any(
        _metric_text_blob(overlay.get("name"), overlay.get("display_summary"), overlay.get("input_layer_names")),
        ["边界", "boundary", "市界", "行政区"],
    ):
        return ""
    overlay_name = _overlay_display_name(overlay)
    return f"按{overlay_name}筛选" if overlay_name else "按边界筛选"


def _location_overlay_artifact(output: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    input_artifacts = _artifact_inputs(output)
    if len(input_artifacts) >= 2:
        return input_artifacts[1]
    observation = dict(item.get("observation") or {})
    data = dict(observation.get("data") or {})
    layer = dict(data.get("layer") or {})
    layer_inputs = _artifact_inputs(layer)
    return layer_inputs[1] if len(layer_inputs) >= 2 else {}


def _primary_input_name(output: dict[str, Any], item: dict[str, Any]) -> str:
    inputs = _artifact_inputs(output)
    if inputs:
        return _overlay_display_name(inputs[0])
    observation = dict(item.get("observation") or {})
    data = dict(observation.get("data") or {})
    layer = dict(data.get("layer") or {})
    layer_inputs = _artifact_inputs(layer)
    if layer_inputs:
        return _overlay_display_name(layer_inputs[0])
    action_input = dict(item.get("action_input") or {})
    return str(action_input.get("input_ref") or "").strip()


def _artifact_inputs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    lineage = dict(payload.get("lineage") or {})
    return [
        dict(item)
        for item in list(payload.get("input_artifacts") or lineage.get("input_artifacts") or [])
        if isinstance(item, dict)
    ]


def _overlay_scope_label(overlay: dict[str, Any]) -> str:
    source_action = str(overlay.get("source_action") or overlay.get("algorithm_id") or "").strip().lower()
    if source_action in {"buffer_layer", "native:buffer"}:
        base = _overlay_base_name(overlay)
        distance = _overlay_distance_text(overlay)
        if base and distance:
            return f"{base} {distance}内"
        if base:
            return f"{base}范围内"
        return "缓冲范围内"
    overlay_text = _metric_text_blob(
        overlay.get("name"),
        overlay.get("display_summary"),
        overlay.get("input_layer_names"),
    )
    if _contains_any(overlay_text, ["边界", "boundary", "市界", "行政区"]):
        return "边界内"
    return ""


def _overlay_display_name(overlay: dict[str, Any]) -> str:
    return str(overlay.get("name") or overlay.get("layer_id") or overlay.get("artifact_id") or "").strip()


def _overlay_base_name(overlay: dict[str, Any]) -> str:
    input_names = [str(item) for item in list(overlay.get("input_layer_names") or []) if str(item or "").strip()]
    if input_names:
        return input_names[0]
    return str(overlay.get("name") or overlay.get("layer_id") or overlay.get("artifact_id") or "").strip()


def _tool_distance_text(output: dict[str, Any], item: dict[str, Any]) -> str:
    artifact_parameters = dict(output.get("parameters") or {})
    if artifact_parameters:
        return _overlay_distance_text({"parameters": artifact_parameters})
    action_input = dict(item.get("action_input") or {})
    if action_input:
        return _overlay_distance_text({"parameters": action_input})
    return ""


def _overlay_distance_text(overlay: dict[str, Any]) -> str:
    parameters = dict(overlay.get("parameters") or {})
    distance = parameters.get("distance", parameters.get("DISTANCE"))
    if distance in (None, ""):
        return ""
    unit = str(parameters.get("unit") or parameters.get("UNIT") or "").strip().lower()
    value = str(distance).strip()
    if not value:
        return ""
    if unit in {"meter", "meters", "m", "米"}:
        return f"{value} 米"
    if unit in {"kilometer", "kilometers", "km", "公里", "千米"}:
        return f"{value} 公里"
    return _distance_phrase(value) or f"{value} 米"


def _tool_output_record(item: dict[str, Any]) -> dict[str, Any]:
    artifact = dict(item.get("output_artifact") or {})
    if artifact:
        return artifact
    observation = dict(item.get("observation") or {})
    data = dict(observation.get("data") or {})
    layer = data.get("layer")
    if isinstance(layer, dict):
        metadata = dict(layer.get("metadata") or {})
        artifact_metadata = dict(metadata.get("artifact") or {})
        lineage = dict(layer.get("lineage") or artifact_metadata.get("lineage") or {})
        return {
            "name": str(layer.get("name") or layer.get("layer_id") or ""),
            "kind": str(layer.get("kind") or ""),
            "feature_count": metadata.get("feature_count"),
            "row_count": metadata.get("row_count"),
            "geometry_type": metadata.get("geometry_type"),
            "crs": metadata.get("crs"),
            "input_artifacts": list(layer.get("input_artifacts") or artifact_metadata.get("input_artifacts") or lineage.get("input_artifacts") or []),
            "input_layer_names": list(layer.get("input_layer_names") or artifact_metadata.get("input_layer_names") or lineage.get("input_layer_names") or []),
            "parameters": dict(layer.get("parameters") or artifact_metadata.get("parameters") or lineage.get("parameters") or {}),
            "source_action": str(layer.get("source_action") or artifact_metadata.get("source_action") or lineage.get("source_action") or ""),
            "lineage": lineage,
        }
    return observation


def _metric_text_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            parts.extend(str(item) for item in value.values() if isinstance(item, (str, int, float)))
            for nested in value.values():
                if isinstance(nested, dict):
                    parts.append(_metric_text_blob(nested))
        elif value is not None:
            parts.append(str(value))
    return " ".join(part for part in parts if part)


def _count_metric(record: dict[str, Any], *, label: str, action: str = "", step_index: int = 0) -> dict[str, Any]:
    payload = dict(record or {})
    if not payload:
        return {}
    count_kind = "feature_count"
    value = payload.get("feature_count")
    if value is None:
        value = payload.get("row_count")
        count_kind = "row_count"
    if value is None:
        metadata = dict(payload.get("metadata") or {})
        value = metadata.get("feature_count")
        if value is None:
            value = metadata.get("row_count")
            count_kind = "row_count"
    if value is None:
        return {}
    title = str(label or payload.get("name") or payload.get("layer_id") or "").strip()
    if not title:
        title = display_title_for_action(action) if action else "结果"
    return make_json_safe(
        {
            "label": title,
            "value": value,
            "unit": "行" if count_kind == "row_count" or str(payload.get("kind") or "").strip().lower() == "table" else "要素",
            "kind": count_kind,
            "action": action,
            "step_index": step_index,
            "layer_name": str(payload.get("name") or payload.get("layer_id") or ""),
        }
    )


def _output_delivery(output: dict[str, Any]) -> dict[str, Any]:
    if not output:
        return {}
    return make_json_safe(
        {
            "name": str(output.get("name") or output.get("layer_id") or output.get("artifact_id") or ""),
            "path": str(output.get("path") or output.get("source") or ""),
            "file_name": str(output.get("file_name") or Path(str(output.get("path") or "")).name or ""),
            "kind": str(output.get("kind") or ""),
            "crs": str(output.get("crs") or ""),
            "geometry_type": str(output.get("geometry_type") or ""),
            "feature_count": output.get("feature_count"),
            "row_count": output.get("row_count"),
        }
    )


def _dedupe_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in steps:
        key = (item.get("step_index"), item.get("action"), item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_metrics(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in metrics:
        key = (item.get("step_index"), item.get("action"), item.get("label"), item.get("value"), item.get("kind"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:8]


def _contains_any(text: str, needles: list[str]) -> bool:
    lowered = str(text or "").lower()
    return any(needle.lower() in lowered for needle in needles)


def _distance_phrase(text: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(米|m|公里|千米|km)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    value, unit = match.group(1), match.group(2)
    normalized_unit = {"m": "米", "km": "公里"}.get(unit.lower(), unit)
    return f"{value} {normalized_unit}"


def _target_name(text: str, markers: list[str], *, fallback: str) -> str:
    raw = str(text or "")
    for marker in markers:
        if marker == "边界":
            match = re.search(r"([\u4e00-\u9fffA-Za-z0-9_]{1,12}(?:市|县|区|省|州|盟)?)边界", raw)
            if match:
                return f"{_clean_target_prefix(match.group(1))}边界"
        index = raw.lower().find(marker.lower())
        if index < 0:
            continue
        start = max(0, index - 8)
        prefix = raw[start:index].strip(" ，,。然后并且且、把将")
        token = prefix.split()[-1] if prefix.split() else prefix
        if token:
            if marker in token:
                return token
            separator = " " if marker.isascii() else ""
            return f"{token}{separator}{marker}"
    return fallback


def _with_target(verb: str, target: str) -> str:
    return f"{verb}{target}" if target else verb


def _clean_target_prefix(value: str) -> str:
    text = str(value or "").strip()
    for marker in ("位于", "处于", "在", "且", "并", "及", "和"):
        if marker in text:
            text = text.split(marker)[-1].strip()
    return text


def _nonblocking_notice_count(payload: dict[str, Any]) -> int:
    warnings = [item for item in list(dict(payload.get("report_audit") or {}).get("warnings") or []) if isinstance(item, dict)]
    quality = [item for item in list(payload.get("quality_findings") or []) if isinstance(item, dict) and not item.get("blocking")]
    return len(warnings) + len(quality)


def _is_final_output(output: dict[str, Any]) -> bool:
    role = str(output.get("role") or "").lower()
    algorithm_id = str(output.get("algorithm_id") or "").lower()
    return role == "final" or algorithm_id == "export_result"


def _source_resume_sentence(report_audit: dict[str, Any]) -> str:
    source_loads = [dict(item) for item in list(report_audit.get("source_loads") or []) if isinstance(item, dict)]
    if not source_loads:
        return ""
    resume_loads = [item for item in source_loads if str(item.get("phase") or "").strip() == "resume"]
    focus = resume_loads[0] if resume_loads else source_loads[0]
    message = str(focus.get("message") or "").strip()
    if message:
        return f"执行过程中{message}"
    source = dict(focus.get("source") or {})
    alias = str(focus.get("alias") or source.get("alias") or source.get("path") or "数据源").strip()
    intent = display_title_for_action(str(focus.get("active_intent") or ""))
    if intent:
        return f"执行过程中补充了 {alias}，并恢复{intent}。"
    return f"执行过程中补充了 {alias}。"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
