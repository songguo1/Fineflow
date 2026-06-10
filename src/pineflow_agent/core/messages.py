"""Localized message catalog for validation and repair prompts."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = {"zh-CN", "en-US"}
_LOCALE: ContextVar[str] = ContextVar("pineflow_locale", default=DEFAULT_LOCALE)


MESSAGE_CATALOG: dict[str, dict[str, str]] = {
    "zh-CN": {
        "semantic.missing_slots": "还需要补充：{slots}。",
        "semantic.buffer.missing_distance": "请告诉我缓冲距离，例如 500 米。",
        "semantic.clip.missing_overlay_ref": "请告诉我要用哪个边界或叠加图层来裁剪。",
        "semantic.reproject.missing_target_crs": "请告诉我目标坐标系，例如 EPSG:3857 或 EPSG:4326。",
        "semantic.export.missing_output_path": "请提供导出输出路径，例如 E:/project/qgis_ai/.pineflow/outputs/result.gpkg。",
        "semantic.invalid_distance": "缓冲距离需要是大于 0 的数字，例如 500 米或 1 公里。",
        "semantic.unsupported_unit": "暂不支持距离单位 {unit}，请使用米或公里。",
        "semantic.field.missing_field": "请提供属性字段名。",
        "semantic.keep_fields.missing_fields": "请提供要保留的字段列表。",
        "semantic.rename_field.missing_field_name": "请提供新的字段名。",
        "semantic.attribute.missing_operator": "请告诉我要使用的属性运算符，例如 =、!=、contains 或 is_null。",
        "semantic.attribute.missing_value": "请提供要匹配的属性值。",
        "semantic.expression.missing_expression": "请提供筛选表达式，例如 \"type\" = 'park'。",
        "semantic.spatial.missing_predicate": "请告诉我要使用的空间关系，例如 intersects、within 或 contains。",
        "semantic.location.missing_intersect_ref": "请告诉我要用哪个参考图层做空间筛选。",
        "semantic.join.missing_join_ref": "请告诉我要连接哪个图层。",
        "semantic.field_calculator.missing_field_name": "请提供要创建或更新的字段名。",
        "semantic.field_calculator.missing_formula": "请提供字段计算使用的 QGIS 表达式。",
        "semantic.unsupported_attribute_operator": "不支持该属性运算符。请使用 =、!=、>、>=、<、<=、contains、is_null 或 is_not_null。",
        "semantic.unsupported_spatial_predicate": "不支持该空间关系。请使用 intersects、contains、within、touches、overlaps、crosses 或 disjoint。",
        "semantic.unsupported_field_type": "不支持该字段类型。请使用 float、integer、string 或 date。",
        "semantic.csv.missing_coordinate_fields": "请提供 CSV 坐标字段，例如 x_field=longitude、y_field=latitude。",
        "semantic.source_required": "当前会话里还没有可用的{slot_label}，请补充一个{source_label}文件后继续。",
        "preflight.buffer.geographic_crs": "图层 {layer} 当前坐标系是 {crs}，不适合直接按 {unit} 做距离缓冲。",
        "preflight.clip.crs_mismatch": "输入图层 {input_layer} 的坐标系是 {input_crs}，叠加图层 {overlay_layer} 的坐标系是 {overlay_crs}，执行前建议统一坐标系。",
        "preflight.unknown_layer": "找不到图层 {layer}，请从已加载图层中选择一个。",
        "preflight.unknown_field": "图层 {layer} 不包含字段：{fields}。",
        "preflight.spatial_predicate_geometry_mismatch": "空间关系 {predicate} 与图层几何组合不匹配：{input_layer}({input_geometry}) / {overlay_layer}({overlay_geometry})。",
        "preflight.not_csv_table": "图层 {layer} 不是已加载的 CSV 表。",
        "preflight.output_exists": "输出文件已存在：{output_path}。",
        "repair.reproject_before_buffer": "建议先将 {layer} 重投影到 {target_crs}，再执行距离缓冲。",
        "repair.reproject_overlay_for_clip": "建议先将叠加图层 {overlay_layer} 重投影到 {target_crs}，再继续执行。",
        "repair.confirm_output_overwrite": "确认覆盖已有输出文件 {output_path}，或取消后指定新的输出路径。",
        "runtime.invalid_geometry": "执行 {action} 时，图层 {layer} 存在无效几何。",
        "repair.fix_geometries": "对 {layer} 执行几何修复，然后重试原操作。",
        "repair.rejected": "已拒绝建议修复。请修改任务描述后继续，或取消当前任务。",
    },
    "en-US": {
        "semantic.missing_slots": "Missing required parameter(s): {slots}.",
        "semantic.buffer.missing_distance": "Please provide the buffer distance, for example 500 meters.",
        "semantic.clip.missing_overlay_ref": "Please provide the boundary or overlay layer for clipping.",
        "semantic.reproject.missing_target_crs": "Please provide the target CRS, for example EPSG:3857 or EPSG:4326.",
        "semantic.export.missing_output_path": "Please provide an export output path, for example E:/project/qgis_ai/.pineflow/outputs/result.gpkg.",
        "semantic.invalid_distance": "Buffer distance must be a number greater than 0, for example 500 meters or 1 kilometer.",
        "semantic.unsupported_unit": "Unsupported distance unit {unit}. Please use meters or kilometers.",
        "semantic.field.missing_field": "Please provide the attribute field name.",
        "semantic.keep_fields.missing_fields": "Please provide the list of fields to keep.",
        "semantic.rename_field.missing_field_name": "Please provide the new field name.",
        "semantic.attribute.missing_operator": "Please provide the attribute operator, for example =, !=, contains, or is_null.",
        "semantic.attribute.missing_value": "Please provide the attribute value to match.",
        "semantic.expression.missing_expression": "Please provide a filter expression, for example \"type\" = 'park'.",
        "semantic.spatial.missing_predicate": "Please provide the spatial predicate, for example intersects, within, or contains.",
        "semantic.location.missing_intersect_ref": "Please provide the reference layer used for the spatial extraction.",
        "semantic.join.missing_join_ref": "Please provide the layer to join from.",
        "semantic.field_calculator.missing_field_name": "Please provide the field name to create or update.",
        "semantic.field_calculator.missing_formula": "Please provide a QGIS expression formula for the field calculation.",
        "semantic.unsupported_attribute_operator": "Unsupported attribute operator. Use =, !=, >, >=, <, <=, contains, is_null, or is_not_null.",
        "semantic.unsupported_spatial_predicate": "Unsupported spatial predicate. Use intersects, contains, within, touches, overlaps, crosses, or disjoint.",
        "semantic.unsupported_field_type": "Unsupported field type. Use float, integer, string, or date.",
        "semantic.csv.missing_coordinate_fields": "Please provide the CSV coordinate fields, for example x_field=longitude and y_field=latitude.",
        "semantic.source_required": "No usable {slot_label} is currently loaded. Please attach a {source_label} file and continue.",
        "preflight.buffer.geographic_crs": "Layer {layer} uses {crs}, which is not suitable for direct distance buffering in {unit}.",
        "preflight.clip.crs_mismatch": "Input layer {input_layer} uses {input_crs}, while overlay layer {overlay_layer} uses {overlay_crs}. Reprojection is recommended first.",
        "preflight.unknown_layer": "Layer {layer} was not found. Please choose one of the loaded layers.",
        "preflight.unknown_field": "Layer {layer} does not contain field(s): {fields}.",
        "preflight.spatial_predicate_geometry_mismatch": "Spatial predicate {predicate} does not fit the layer geometry combination: {input_layer}({input_geometry}) / {overlay_layer}({overlay_geometry}).",
        "preflight.not_csv_table": "Layer {layer} is not a loaded CSV table.",
        "preflight.output_exists": "Output file already exists: {output_path}.",
        "repair.reproject_before_buffer": "Reproject {layer} to {target_crs} before running the distance buffer.",
        "repair.reproject_overlay_for_clip": "Reproject overlay layer {overlay_layer} to {target_crs} before continuing.",
        "repair.confirm_output_overwrite": "Confirm overwriting existing output file {output_path}, or cancel and provide a new output path.",
        "runtime.invalid_geometry": "Layer {layer} has invalid geometry while running {action}.",
        "repair.fix_geometries": "Fix geometries for {layer}, then retry the original action.",
        "repair.rejected": "The suggested repair was rejected. Please revise the GIS task or cancel the current task.",
    },
}


SLOT_LABELS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "input_ref": "输入图层",
        "overlay_ref": "叠加/裁剪图层",
        "distance": "缓冲距离",
        "input_refs": "至少两个待合并图层",
        "target_crs": "目标坐标系",
        "field": "属性字段",
        "fields": "保留字段列表",
        "field_name": "输出字段名",
        "operator": "属性运算符",
        "value": "属性值",
        "predicate": "空间关系",
        "intersect_ref": "相交参考图层",
        "join_ref": "连接图层",
        "formula": "字段计算表达式",
        "expression": "筛选表达式",
        "x_field": "CSV 经度/X 字段",
        "y_field": "CSV 纬度/Y 字段",
        "output_path": "输出路径",
    },
    "en-US": {
        "input_ref": "input layer",
        "overlay_ref": "overlay layer",
        "distance": "buffer distance",
        "input_refs": "at least two input layers",
        "target_crs": "target CRS",
        "field": "attribute field",
        "fields": "fields to keep",
        "field_name": "output field name",
        "operator": "attribute operator",
        "value": "attribute value",
        "predicate": "spatial predicate",
        "intersect_ref": "intersecting layer",
        "join_ref": "join layer",
        "formula": "field calculation formula",
        "expression": "filter expression",
        "x_field": "CSV longitude/x field",
        "y_field": "CSV latitude/y field",
        "output_path": "output path",
    },
}


def set_locale(locale: str) -> None:
    _LOCALE.set(normalize_locale(locale))


def get_locale() -> str:
    return _LOCALE.get()


def normalize_locale(locale: str) -> str:
    text = str(locale or "").strip()
    return text if text in SUPPORTED_LOCALES else DEFAULT_LOCALE


def render_message(message_key: str, params: dict[str, Any] | None = None, locale: str | None = None) -> str:
    selected = normalize_locale(locale or get_locale())
    template = MESSAGE_CATALOG.get(selected, MESSAGE_CATALOG[DEFAULT_LOCALE]).get(
        message_key,
        MESSAGE_CATALOG[DEFAULT_LOCALE].get(message_key, message_key),
    )
    values = dict(params or {})
    if "missing_slots" in values and "slots" not in values:
        values["slots"] = format_slots(list(values.get("missing_slots") or []), locale=selected)
    try:
        return template.format(**values)
    except Exception:
        return template


def format_slots(slots: list[str], *, locale: str | None = None) -> str:
    selected = normalize_locale(locale or get_locale())
    labels = SLOT_LABELS.get(selected, SLOT_LABELS[DEFAULT_LOCALE])
    separator = "、" if selected == "zh-CN" else ", "
    return separator.join(labels.get(slot, slot) for slot in slots)
