"""Natural-language formatting for structured state query results."""

from __future__ import annotations

from typing import Any

from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action

from pineflow_api.application.state_query import StateQueryResult

FIELD_PREVIEW_LIMIT = 12
SUMMARY_INTERMEDIATE_LIMIT = 8
OUTPUT_PREVIEW_LIMIT = 5


class StateAnswerFormatter:
    """Render structured state query results for the desktop/chat channel."""

    def format(self, query: StateQueryResult | dict[str, Any]) -> str:
        query_payload = _query_payload(query)
        if not bool(query_payload.get("has_state")):
            return "当前会话还没有可用图层或输出。请先加载数据或执行一个 GIS 任务。"
        answer_type = str(query_payload.get("answer_type") or "summary")
        layers = [dict(item) for item in list(query_payload.get("layers") or []) if isinstance(item, dict)]
        outputs = [dict(item) for item in list(query_payload.get("outputs") or []) if isinstance(item, dict)]
        intermediate_outputs = [
            dict(item) for item in list(query_payload.get("intermediate_outputs") or []) if isinstance(item, dict)
        ]
        if answer_type == "fields":
            return _fields_message(layers)
        if answer_type == "layers":
            return _layers_message(layers)
        if answer_type == "crs":
            return _crs_message(layers)
        if answer_type == "outputs":
            return _outputs_message(
                outputs,
                [dict(item) for item in list(query_payload.get("legacy_trace_outputs") or []) if isinstance(item, dict)],
                intermediate_count=len(intermediate_outputs),
            )
        if answer_type == "last_step":
            return _last_step_message(dict(query_payload.get("last_step") or {}))
        return _state_summary_message(layers, outputs, intermediate_outputs)


def _query_payload(query: StateQueryResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(query, StateQueryResult):
        return query.to_dict()
    return dict(query or {})


def _fields_message(layers: list[dict[str, Any]]) -> str:
    if not layers:
        return "当前会话没有已加载图层，因此没有可查看的字段。"
    lines = ["当前图层字段如下："]
    for layer in layers:
        fields = _field_names(dict(layer.get("metadata") or {}).get("fields"))
        if fields:
            lines.append(f"- {_layer_title(layer)}：{len(fields)} 个字段；{_field_preview(fields)}")
        else:
            lines.append(f"- {_layer_title(layer)}：未记录字段信息")
    return "\n".join(lines)


def _layers_message(layers: list[dict[str, Any]]) -> str:
    if not layers:
        return "当前会话没有已加载图层。"
    lines = ["当前会话图层如下："]
    for layer in layers:
        lines.append(f"- {_data_summary_line(layer)}")
    return "\n".join(lines)


def _crs_message(layers: list[dict[str, Any]]) -> str:
    if not layers:
        return "当前会话没有已加载图层，因此没有 CRS 信息。"
    lines = ["当前图层 CRS 信息如下："]
    for layer in layers:
        metadata = dict(layer.get("metadata") or {})
        lines.append(f"- {_layer_title(layer)}：{metadata.get('crs') or 'unknown'}")
    return "\n".join(lines)


def _outputs_message(outputs: list[dict[str, Any]], legacy_outputs: list[dict[str, Any]], *, intermediate_count: int = 0) -> str:
    if not outputs:
        outputs = legacy_outputs
    if not outputs:
        if intermediate_count:
            return (
                f"当前会话还没有最终输出文件；本次流程已生成 {intermediate_count} 个中间图层。"
                "临时处理路径默认不在聊天中展开，可在右侧“结果/状态文件”查看完整记录。"
            )
        return "当前会话还没有记录到输出文件。"
    final_outputs = [output for output in outputs if _is_final_output(output)]
    intermediate_outputs = [output for output in outputs if not _is_final_output(output)]

    if final_outputs:
        lines = ["当前主要输出："]
        for output in final_outputs[:OUTPUT_PREVIEW_LIMIT]:
            lines.extend(_output_lines(output))
        if len(final_outputs) > OUTPUT_PREVIEW_LIMIT:
            lines.append(f"- 另有 {len(final_outputs) - OUTPUT_PREVIEW_LIMIT} 个最终输出未在聊天中展开。")
        if intermediate_count:
            lines.append("")
            lines.append(
                f"中间结果：本次流程还生成了 {intermediate_count} 个中间图层，"
                "默认不在聊天中展开临时路径；可在右侧“结果/状态文件”查看完整记录。"
            )
        return "\n".join(lines)

    stable_outputs = [output for output in outputs if not _is_temp_path(_item_path(output))]
    preview = stable_outputs[:OUTPUT_PREVIEW_LIMIT] or outputs[-OUTPUT_PREVIEW_LIMIT:]
    title = "当前记录到的输出：" if stable_outputs else "当前只有中间结果："
    lines = [title]
    for output in preview:
        lines.extend(_output_lines(output))
    remaining = len(outputs) - len(preview)
    if remaining > 0:
        lines.append(f"- 另有 {remaining} 个中间输出未展开。")
    return "\n".join(lines)


def _last_step_message(step: dict[str, Any]) -> str:
    if step:
        observation = dict(step.get("observation") or {})
        action = str(step.get("action") or "unknown")
        action_title = display_title_for_action(action)
        message = str(observation.get("message") or "")
        output_path = str(observation.get("output_path") or "")
        if output_path:
            return f"上一步成功执行 `{action_title}`：{message}\n\n输出文件：{_short_path(output_path)}"
        return f"上一步成功执行 `{action_title}`：{message}"
    return "当前会话还没有成功的工具步骤记录。"


def _state_summary_message(
    layers: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    intermediate_outputs: list[dict[str, Any]],
) -> str:
    final_outputs = [output for output in outputs if _is_final_output(output)]
    artifact_intermediates = [output for output in intermediate_outputs if not _is_final_output(output)]
    input_layers = [layer for layer in layers if _is_input_layer(layer)]
    derived_layers = [layer for layer in layers if not _is_input_layer(layer)]

    lines = ["当前会话可用数据："]
    if final_outputs:
        lines.append("")
        lines.append("最终结果：")
        for output in final_outputs[:OUTPUT_PREVIEW_LIMIT]:
            lines.append(f"- {_data_summary_line(output)}")
            path = _short_path(_item_path(output))
            if path:
                lines.append(f"  文件：{path}")

    if input_layers:
        lines.append("")
        lines.append("输入数据：")
        for layer in input_layers:
            lines.append(f"- {_data_summary_line(layer)}")

    key_intermediates = _key_intermediate_items(artifact_intermediates, derived_layers)
    if key_intermediates:
        lines.append("")
        lines.append("关键中间数据：")
        for item in key_intermediates[:SUMMARY_INTERMEDIATE_LIMIT]:
            lines.append(f"- {_data_summary_line(item)}")
        remaining = len(key_intermediates) - SUMMARY_INTERMEDIATE_LIMIT
        if remaining > 0:
            lines.append(f"- 另有 {remaining} 个中间图层未展开。")

    lines.append("")
    lines.append(f"总计：{len(layers)} 个图层、{len(outputs)} 个输出记录。临时处理文件默认不在聊天中展开完整路径。")
    return "\n".join(lines)


def _layer_title(layer: dict[str, Any]) -> str:
    name = _item_name(layer)
    layer_id = str(layer.get("layer_id") or "").strip()
    return f"{name} [{layer_id}]" if layer_id and layer_id != name else name


def _data_summary_line(item: dict[str, Any]) -> str:
    parts = _metadata_parts(item)
    suffix = f"（{'，'.join(parts)}）" if parts else ""
    action = _algorithm_label(item)
    action_suffix = f"；来源：{action}" if action else ""
    return f"{_item_name(item)}{suffix}{action_suffix}"


def _output_lines(output: dict[str, Any]) -> list[str]:
    summary = str(output.get("display_summary") or "").strip()
    lines = [f"- {summary}" if summary else f"- {_data_summary_line(output)}"]
    extra_lines = [
        line
        for line in list(output.get("summary_lines") or [])
        if isinstance(line, str) and line.strip() and line.strip() != summary
    ]
    for line in extra_lines[:2]:
        if line.startswith("文件："):
            continue
        lines.append(f"  {line}")
    path = _short_path(_item_path(output))
    if path:
        lines.append(f"  文件：{path}")
    return lines


def _metadata_parts(item: dict[str, Any]) -> list[str]:
    metadata = dict(item.get("metadata") or {})
    parts: list[str] = []
    kind = str(item.get("kind") or "").strip()
    if kind:
        parts.append(_kind_label(kind))
    count = _count_text(item, metadata)
    if count:
        parts.append(count)
    crs = str(item.get("crs") or metadata.get("crs") or "").strip()
    if crs:
        parts.append(crs)
    geometry = str(item.get("geometry_type") or metadata.get("geometry_type") or "").strip()
    if geometry and geometry.lower() != "none":
        parts.append(geometry)
    return parts


def _count_text(item: dict[str, Any], metadata: dict[str, Any]) -> str:
    row_count = item.get("row_count", metadata.get("row_count"))
    if row_count is not None:
        return f"{_format_count(row_count)} 行"
    feature_count = item.get("feature_count", metadata.get("feature_count"))
    if feature_count is not None:
        return f"{_format_count(feature_count)} 要素"
    return ""


def _format_count(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _kind_label(kind: str) -> str:
    labels = {
        "vector": "矢量",
        "raster": "栅格",
        "table": "表格",
        "csv": "表格",
    }
    return labels.get(kind, kind)


def _algorithm_label(item: dict[str, Any]) -> str:
    algorithm_id = str(item.get("algorithm_id") or "").strip()
    if algorithm_id:
        return display_title_for_action(algorithm_id)
    source_action = str(item.get("source_action") or "").strip()
    return display_title_for_action(source_action) if source_action else ""


def _item_name(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    path_name = _path_stem(_item_path(item))
    if not name or name in {"layer", "output", "unnamed_layer"}:
        return path_name or str(item.get("layer_id") or "unnamed_layer")
    return name


def _item_path(item: dict[str, Any]) -> str:
    return str(item.get("path") or item.get("output_path") or item.get("source") or "").strip()


def _path_stem(path: str) -> str:
    filename = _path_filename(path)
    if "." not in filename:
        return filename
    return ".".join(filename.split(".")[:-1]) or filename


def _path_filename(path: str) -> str:
    normalized = str(path or "").replace("/", "\\")
    return normalized.split("\\")[-1] if normalized else ""


def _short_path(path: str) -> str:
    normalized = str(path or "").replace("/", "\\").strip()
    if not normalized:
        return ""
    filename = _path_filename(normalized)
    if _is_temp_path(normalized):
        return f"临时会话文件：{filename}"
    parts = [part for part in normalized.split("\\") if part]
    if len(parts) >= 2:
        return f"...\\{parts[-2]}\\{parts[-1]}"
    return filename or normalized


def _is_temp_path(path: str) -> bool:
    normalized = str(path or "").replace("/", "\\").lower()
    return "\\.pineflow\\sessions\\" in normalized and "\\temp\\" in normalized


def _is_final_output(output: dict[str, Any]) -> bool:
    role = str(output.get("role") or "").lower()
    algorithm_id = str(output.get("algorithm_id") or "").lower()
    path = _item_path(output)
    return role == "final" or algorithm_id == "export_result" or (bool(path) and not _is_temp_path(path) and role != "intermediate")


def _is_input_layer(layer: dict[str, Any]) -> bool:
    artifact_role = str(layer.get("artifact_role") or layer.get("role") or "").strip().lower()
    if artifact_role == "input":
        return True
    algorithm_id = str(layer.get("algorithm_id") or "").strip()
    parent_ids = layer.get("parent_ids") or []
    source = _item_path(layer)
    return not algorithm_id and not parent_ids and not _is_temp_path(source)


def _key_intermediate_items(outputs: list[dict[str, Any]], derived_layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if outputs:
        return [output for output in outputs if not _is_final_output(output)]
    return [layer for layer in derived_layers if not _is_final_output(layer)]


def _field_preview(fields: list[str], limit: int = FIELD_PREVIEW_LIMIT) -> str:
    if not fields:
        return "未记录字段信息"
    visible = fields[:limit]
    suffix = f"；另有 {len(fields) - limit} 个字段" if len(fields) > limit else ""
    return f"{', '.join(visible)}{suffix}"


def _field_names(fields: Any) -> list[str]:
    names: list[str] = []
    for field in list(fields or []):
        if isinstance(field, dict):
            value = field.get("name") or field.get("field_name") or field.get("id")
        else:
            value = field
        text = str(value or "").strip()
        if text:
            names.append(text)
    return names
