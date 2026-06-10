"""Semantic GIS tool schemas mapped to QGIS processing algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

import yaml

from pineflow_agent.core.messages import render_message
from pineflow_agent.core.models import ActionPlan
from pineflow_agent.rules.rule_registry import RuleEvaluationContext, RuleRegistry
from pineflow_agent.rules.validation import RepairProposal, ValidationIssue


@dataclass(frozen=True)
class SemanticToolSchema:
    action: str
    algorithm_id: str
    required_slots: tuple[str, ...]
    defaults: dict[str, Any] = field(default_factory=dict)
    processing_parameters: dict[str, Any] = field(default_factory=dict)
    output_policy: dict[str, Any] = field(default_factory=dict)
    missing_slot_messages: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def contract(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "algorithm_id": self.algorithm_id,
            "required_slots": list(self.required_slots),
            "defaults": dict(self.defaults),
            "processing_parameters": dict(self.processing_parameters),
            "output_policy": dict(self.output_policy),
            "missing_slot_messages": dict(self.missing_slot_messages),
        }


SEMANTIC_DEFS_DIR = Path(__file__).resolve().parents[1] / "contracts" / "defs" / "semantic"


def _load_semantic_tool_schemas() -> dict[str, SemanticToolSchema]:
    schemas: dict[str, SemanticToolSchema] = {}
    for yaml_file in sorted(SEMANTIC_DEFS_DIR.glob("*.yaml")):
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        name = str(data.get("name") or yaml_file.stem).strip()
        if not name:
            continue
        algorithm_id = str(data.get("algorithm_id") or "").strip()
        if not algorithm_id:
            continue
        schemas[name] = SemanticToolSchema(
            action=name,
            algorithm_id=algorithm_id,
            required_slots=tuple(str(slot) for slot in list(data.get("required_slots") or ()) if str(slot)),
            defaults=dict(data.get("defaults") or {}),
            processing_parameters=dict(data.get("processing_parameters") or {}),
            output_policy=dict(data.get("output_policy") or {}),
            missing_slot_messages=dict(data.get("missing_slot_messages") or {}),
            description=str(data.get("description") or ""),
        )
    return schemas


SEMANTIC_TOOL_SCHEMAS: dict[str, SemanticToolSchema] = _load_semantic_tool_schemas()

ALIASES: dict[str, dict[str, str]] = {
    "buffer_layer": {"layer_ref": "input_ref", "input_layer": "input_ref", "buffer_distance": "distance"},
    "clip_layer": {"layer_ref": "input_ref", "clip_ref": "overlay_ref", "overlay_layer": "overlay_ref"},
    "dissolve_layer": {"layer_ref": "input_ref", "field": "dissolve_field"},
    "merge_layers": {"layers": "input_refs", "layer_refs": "input_refs"},
    "reproject_layer": {"layer_ref": "input_ref", "crs": "target_crs"},
    "intersect_layer": {"layer_ref": "input_ref", "overlay_layer": "overlay_ref"},
    "difference_layer": {"layer_ref": "input_ref", "overlay_layer": "overlay_ref"},
    "extract_by_attribute": {"layer_ref": "input_ref", "attribute": "field"},
    "keep_fields": {"layer_ref": "input_ref", "field_names": "fields", "keep_fields": "fields"},
    "rename_field": {"layer_ref": "input_ref", "old_field": "field", "new_field": "field_name", "new_name": "field_name"},
    "select_by_expression": {"layer_ref": "input_ref", "formula": "expression", "filter_expression": "expression"},
    "extract_by_location": {"layer_ref": "input_ref", "overlay_ref": "intersect_ref", "overlay_layer": "intersect_ref"},
    "join_by_location": {"layer_ref": "input_ref", "overlay_ref": "join_ref", "overlay_layer": "join_ref"},
    "field_calculator": {"layer_ref": "input_ref", "new_field": "field_name", "expression": "formula"},
    "csv_to_points": {"table_ref": "input_ref", "csv_ref": "input_ref", "lon_field": "x_field", "lat_field": "y_field"},
    "fix_geometries": {"layer_ref": "input_ref"},
    "union_layer": {"layer_ref": "input_ref", "overlay_layer": "overlay_ref"},
    "symmetrical_difference": {"layer_ref": "input_ref", "overlay_layer": "overlay_ref"},
    "centroid_layer": {"layer_ref": "input_ref"},
    "point_on_surface": {"layer_ref": "input_ref"},
    "multipart_to_singlepart": {"layer_ref": "input_ref"},
    "simplify_geometry": {"layer_ref": "input_ref", "distance": "tolerance"},
    "delete_duplicate_geometries": {"layer_ref": "input_ref"},
    "snap_geometries": {"layer_ref": "input_ref", "reference_layer": "reference_ref", "snap_ref": "reference_ref", "distance": "tolerance"},
    "check_validity": {"layer_ref": "input_ref"},
    "bounding_boxes": {"layer_ref": "input_ref"},
    "convex_hull": {"layer_ref": "input_ref"},
    "count_points_in_polygon": {"polygons_ref": "polygon_ref", "points_ref": "point_ref"},
    "join_by_nearest": {"layer_ref": "input_ref", "overlay_ref": "join_ref", "overlay_layer": "join_ref"},
    "reproject_raster": {"raster_ref": "input_ref", "crs": "target_crs"},
    "clip_raster_by_mask": {"raster_ref": "input_ref", "overlay_ref": "mask_ref", "mask_layer": "mask_ref"},
    "clip_raster_by_extent": {"raster_ref": "input_ref"},
    "zonal_statistics": {"polygon_ref": "input_ref"},
    "raster_sampling": {"point_ref": "input_ref"},
    "rasterize_vector": {"layer_ref": "input_ref"},
    "polygonize_raster": {"raster_ref": "input_ref"},
    "terrain_ruggedness_index": {"raster_ref": "input_ref"},
    "topographic_position_index": {"raster_ref": "input_ref"},
    "roughness": {"raster_ref": "input_ref"},
}

def register_semantic_validation_rule(
    name: str,
    *actions: str,
) -> Any:
    return RuleRegistry.register(
        name=name,
        stage="semantic",
        actions=tuple(str(action or "").strip() for action in actions if str(action or "").strip()),
    )


def semantic_validation_rules():
    return tuple(rule for rule in RuleRegistry.default().rules if rule.stage == "semantic")


def is_semantic_action(action: str) -> bool:
    return str(action or "").strip() in SEMANTIC_TOOL_SCHEMAS


def normalize_semantic_input(action: str, action_input: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(action_input or {})
    for source, target in ALIASES.get(str(action or ""), {}).items():
        if target not in normalized and source in normalized:
            normalized[target] = normalized[source]
    return normalized


def missing_required_slots(action: str, action_input: dict[str, Any]) -> list[str]:
    schema = SEMANTIC_TOOL_SCHEMAS.get(str(action or ""))
    if schema is None:
        return []
    normalized = normalize_semantic_input(action, action_input)
    missing: list[str] = []
    for slot in schema.required_slots:
        value = normalized.get(slot)
        if slot in {"input_refs", "raster_refs"}:
            minimum = 2 if slot == "input_refs" else 1
            if not isinstance(value, list) or len(value) < minimum:
                missing.append(slot)
            continue
        if value is None or str(value).strip() == "":
            missing.append(slot)
    return missing


def validate_semantic_action(action: str, action_input: dict[str, Any]) -> list[ValidationIssue]:
    if not is_semantic_action(action):
        return []

    normalized = normalize_semantic_input(action, action_input)
    return RuleRegistry.default().issues("semantic", ActionPlan("", action, normalized))


def question_for_missing_slots(action: str, missing_slots: list[str]) -> str:
    if not missing_slots:
        return ""
    return render_message(
        _missing_slots_message_key(action, missing_slots),
        {"action": action, "missing_slots": missing_slots},
    )


def semantic_algorithm_call(action: str, action_input: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    normalized = normalize_semantic_input(action, action_input)
    schema = SEMANTIC_TOOL_SCHEMAS[str(action)]
    output = normalized.get("output_path") or normalized.get("output") or schema.defaults.get("output", "TEMPORARY_OUTPUT")
    output_name = str(normalized.get("output_name") or _default_output_name(action, normalized))

    if schema.processing_parameters:
        return schema.algorithm_id, _processing_parameters_from_yaml(schema, normalized, output=output), output_name

    if action == "buffer_layer":
        params = {
            "INPUT": normalized.get("input_ref"),
            "DISTANCE": _distance_to_meters(normalized.get("distance"), normalized.get("unit")),
            "SEGMENTS": int(normalized.get("segments", schema.defaults["segments"])),
            "DISSOLVE": bool(normalized.get("dissolve", schema.defaults["dissolve"])),
            "OUTPUT": output,
        }
        return schema.algorithm_id, params, output_name

    if action == "dissolve_layer":
        dissolve_field = str(normalized.get("dissolve_field") or "").strip()
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "FIELD": [dissolve_field] if dissolve_field else [],
            "SEPARATE_DISJOINT": bool(normalized.get("separate_disjoint", schema.defaults["separate_disjoint"])),
            "OUTPUT": output,
        }, output_name

    if action == "intersect_layer":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "OVERLAY": normalized.get("overlay_ref"),
            "INPUT_FIELDS": list(normalized.get("input_fields") or []),
            "OVERLAY_FIELDS": list(normalized.get("overlay_fields") or []),
            "OVERLAY_FIELDS_PREFIX": str(normalized.get("overlay_fields_prefix") or ""),
            "OUTPUT": output,
        }, output_name

    if action == "extract_by_attribute":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "FIELD": normalized.get("field"),
            "OPERATOR": _attribute_operator(normalized.get("operator")),
            "VALUE": normalized.get("value"),
            "OUTPUT": output,
        }, output_name

    if action == "extract_by_location":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "PREDICATE": _spatial_predicates(normalized.get("predicate")),
            "INTERSECT": normalized.get("intersect_ref"),
            "OUTPUT": output,
        }, output_name

    if action == "join_by_location":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "JOIN": normalized.get("join_ref"),
            "PREDICATE": _spatial_predicates(normalized.get("predicate")),
            "JOIN_FIELDS": list(normalized.get("join_fields") or schema.defaults["join_fields"]),
            "METHOD": int(normalized.get("method", schema.defaults["method"])),
            "DISCARD_NONMATCHING": bool(normalized.get("discard_nonmatching", schema.defaults["discard_nonmatching"])),
            "PREFIX": str(normalized.get("prefix") or schema.defaults["prefix"]),
            "OUTPUT": output,
        }, output_name

    if action == "csv_to_points":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "XFIELD": normalized.get("x_field"),
            "YFIELD": normalized.get("y_field"),
            "TARGET_CRS": normalized.get("crs") or schema.defaults["crs"],
            "OUTPUT": output,
        }, output_name

    if action == "join_by_nearest":
        max_distance = normalized.get("max_distance", schema.defaults["max_distance"])
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "INPUT_2": normalized.get("join_ref"),
            "FIELDS_TO_COPY": list(normalized.get("join_fields") or schema.defaults["join_fields"]),
            "DISCARD_NONMATCHING": bool(normalized.get("discard_nonmatching", schema.defaults["discard_nonmatching"])),
            "PREFIX": str(normalized.get("prefix") or schema.defaults["prefix"]),
            "NEIGHBORS": int(normalized.get("neighbors", schema.defaults["neighbors"])),
            "MAX_DISTANCE": None if max_distance in {None, ""} else float(max_distance),
            "OUTPUT": output,
        }, output_name

    if action == "reproject_raster":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "TARGET_CRS": normalized.get("target_crs"),
            "RESAMPLING": int(normalized.get("resampling", schema.defaults["resampling"])),
            "NODATA": normalized.get("nodata"),
            "OUTPUT": output,
        }, output_name

    if action == "clip_raster_by_mask":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "MASK": normalized.get("mask_ref"),
            "CROP_TO_CUTLINE": bool(normalized.get("crop_to_cutline", schema.defaults["crop_to_cutline"])),
            "NODATA": normalized.get("nodata"),
            "OUTPUT": output,
        }, output_name

    if action == "clip_raster_by_extent":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "PROJWIN": normalized.get("extent"),
            "NODATA": normalized.get("nodata"),
            "OUTPUT": output,
        }, output_name

    if action == "raster_calculator":
        return schema.algorithm_id, {
            "LAYERS": list(normalized.get("raster_refs") or []),
            "EXPRESSION": normalized.get("expression"),
            "OUTPUT": output,
        }, output_name

    if action == "zonal_statistics":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "INPUT_RASTER": normalized.get("raster_ref"),
            "RASTER_BAND": int(normalized.get("raster_band", schema.defaults["raster_band"])),
            "COLUMN_PREFIX": str(normalized.get("column_prefix") or schema.defaults["column_prefix"]),
            "STATISTICS": list(normalized.get("statistics") or schema.defaults["statistics"]),
            "OUTPUT": output,
        }, output_name

    if action == "raster_sampling":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "RASTERCOPY": normalized.get("raster_ref"),
            "COLUMN_PREFIX": str(normalized.get("column_prefix") or schema.defaults["column_prefix"]),
            "OUTPUT": output,
        }, output_name

    if action == "rasterize_vector":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "FIELD": str(normalized.get("field") or ""),
            "BURN": float(normalized.get("burn_value", schema.defaults["burn_value"])),
            "WIDTH": int(normalized.get("width")),
            "HEIGHT": int(normalized.get("height")),
            "EXTENT": normalized.get("extent"),
            "NODATA": normalized.get("nodata"),
            "OUTPUT": output,
        }, output_name

    if action == "hillshade":
        return schema.algorithm_id, {
            "INPUT": normalized.get("input_ref"),
            "BAND": int(normalized.get("band", schema.defaults["band"])),
            "Z_FACTOR": float(normalized.get("z_factor", schema.defaults["z_factor"])),
            "SCALE": float(normalized.get("scale", schema.defaults["scale"])),
            "AZIMUTH": float(normalized.get("azimuth", schema.defaults["azimuth"])),
            "ALTITUDE": float(normalized.get("altitude", schema.defaults["altitude"])),
            "COMPUTE_EDGES": bool(normalized.get("compute_edges", schema.defaults["compute_edges"])),
            "OUTPUT": output,
        }, output_name

    if action == "reclassify_raster":
        return schema.algorithm_id, {
            "INPUT_RASTER": normalized.get("input_ref"),
            "RASTER_BAND": int(normalized.get("raster_band", schema.defaults["raster_band"])),
            "TABLE": normalized.get("table_ref"),
            "MIN_FIELD": str(normalized.get("min_field") or ""),
            "MAX_FIELD": str(normalized.get("max_field") or ""),
            "VALUE_FIELD": str(normalized.get("value_field") or ""),
            "OUTPUT": output,
        }, output_name

    raise KeyError(f"Unknown semantic action: {action}")


def _processing_parameters_from_yaml(
    schema: SemanticToolSchema,
    action_input: dict[str, Any],
    *,
    output: Any,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for qgis_key, spec in dict(schema.processing_parameters or {}).items():
        params[str(qgis_key)] = _processing_parameter_value(spec, schema, action_input, output=output)
    return params


def _processing_parameter_value(
    spec: Any,
    schema: SemanticToolSchema,
    action_input: dict[str, Any],
    *,
    output: Any,
) -> Any:
    if spec == "__output__":
        return output
    if isinstance(spec, str):
        return action_input.get(spec)
    if not isinstance(spec, dict):
        return spec

    if "value" in spec:
        value = output if spec.get("value") == "__output__" else spec.get("value")
    else:
        slot = str(spec.get("slot") or "")
        value = action_input.get(slot) if slot else None
        if (value is None or value == "") and "default_slot" in spec:
            value = schema.defaults.get(str(spec.get("default_slot") or ""))
        if (value is None or value == "") and "default" in spec:
            value = spec.get("default")
    if spec.get("none_if_empty") and (value is None or value == ""):
        return None

    return _coerce_processing_parameter(value, str(spec.get("type") or ""))


def _coerce_processing_parameter(value: Any, value_type: str) -> Any:
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    if value_type == "bool":
        return bool(value)
    if value_type == "string":
        return str(value)
    if value_type == "list":
        return list(value or [])
    if value_type == "field_type":
        return _field_type(value)
    return value


def _default_output_name(action: str, action_input: dict[str, Any]) -> str:
    input_ref = str(action_input.get("input_ref") or "result").strip() or "result"
    schema = SEMANTIC_TOOL_SCHEMAS.get(str(action or ""))
    if schema is not None:
        fixed_name = str(schema.output_policy.get("fixed_name") or "").strip()
        if fixed_name:
            return fixed_name
        suffix = str(schema.output_policy.get("suffix") or "").strip()
        if suffix:
            return f"{input_ref}_{suffix}"
    suffixes = {
        "buffer_layer": "buffer",
        "clip_layer": "clip",
        "dissolve_layer": "dissolve",
        "merge_layers": "merged",
        "reproject_layer": "reprojected",
        "intersect_layer": "intersection",
        "difference_layer": "difference",
        "extract_by_attribute": "filtered",
        "rename_field": "renamed_field",
        "extract_by_location": "located",
        "join_by_location": "joined",
        "field_calculator": "calculated",
        "csv_to_points": "points",
        "fix_geometries": "fixed",
        "union_layer": "union",
        "symmetrical_difference": "symdiff",
        "centroid_layer": "centroids",
        "point_on_surface": "surface_points",
        "multipart_to_singlepart": "singlepart",
        "simplify_geometry": "simplified",
        "delete_duplicate_geometries": "deduplicated",
        "snap_geometries": "snapped",
        "check_validity": "valid",
        "bounding_boxes": "boxes",
        "convex_hull": "hull",
        "count_points_in_polygon": "point_count",
        "join_by_nearest": "nearest_join",
        "reproject_raster": "reprojected",
        "clip_raster_by_mask": "masked",
        "clip_raster_by_extent": "clipped",
        "raster_calculator": "calculated",
        "zonal_statistics": "zonal",
        "raster_sampling": "sampled",
        "rasterize_vector": "rasterized",
        "polygonize_raster": "polygonized",
        "slope": "slope",
        "aspect": "aspect",
        "hillshade": "hillshade",
        "contour": "contour",
        "reclassify_raster": "reclassified",
        "terrain_ruggedness_index": "tri",
        "topographic_position_index": "tpi",
        "roughness": "roughness",
    }
    return f"{input_ref}_{suffixes.get(action, 'result')}"


def _missing_slots_message_key(action: str, missing_slots: list[str]) -> str:
    schema = SEMANTIC_TOOL_SCHEMAS.get(str(action or ""))
    if schema is not None:
        messages = dict(schema.missing_slot_messages or {})
        for slot in missing_slots:
            message_key = str(messages.get(str(slot)) or "").strip()
            if message_key:
                return message_key
        default_key = str(messages.get("*") or "").strip()
        if default_key:
            return default_key
    if action == "buffer_layer" and "distance" in missing_slots:
        return "semantic.buffer.missing_distance"
    if action == "clip_layer" and "overlay_ref" in missing_slots:
        return "semantic.clip.missing_overlay_ref"
    if action == "reproject_layer" and "target_crs" in missing_slots:
        return "semantic.reproject.missing_target_crs"
    if action in {"extract_by_attribute", "field_calculator"} and "field" in missing_slots:
        return "semantic.field.missing_field"
    if action == "field_calculator" and "formula" in missing_slots:
        return "semantic.field_calculator.missing_formula"
    if action == "csv_to_points" and ("x_field" in missing_slots or "y_field" in missing_slots):
        return "semantic.csv.missing_coordinate_fields"
    return "semantic.missing_slots"


@register_semantic_validation_rule("required_slots")
def _validate_required_slots(context: RuleEvaluationContext) -> list[ValidationIssue]:
    missing = missing_required_slots(context.plan.action, context.action_input)
    if not missing:
        return []
    message_key = _missing_slots_message_key(context.plan.action, missing)
    params = {"action": context.plan.action, "missing_slots": missing}
    return [
        ValidationIssue(
            code="missing_slot",
            stage="semantic",
            severity="error",
            message_key=message_key,
            params=params,
            repair=RepairProposal(kind="ask_user", message_key=message_key, params=params),
        )
    ]


@register_semantic_validation_rule("buffer_distance", "buffer_layer")
def _validate_buffer_distance(context: RuleEvaluationContext) -> list[ValidationIssue]:
    try:
        _distance_to_meters(context.action_input.get("distance"), context.action_input.get("unit"))
    except ValueError as exc:
        code = str(exc)
        message_key = "semantic.unsupported_unit" if code == "unsupported_unit" else "semantic.invalid_distance"
        params = {"action": context.plan.action, "unit": str(context.action_input.get("unit") or "").strip()}
        return [
            ValidationIssue(
                code=code,
                stage="semantic",
                severity="error",
                message_key=message_key,
                params=params,
                repair=RepairProposal(kind="ask_user", message_key=message_key, params=params),
            )
        ]
    return []


@register_semantic_validation_rule("attribute_operator", "extract_by_attribute")
def _validate_attribute_operator(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if "operator" not in context.action_input:
        return []
    try:
        _attribute_operator(context.action_input.get("operator"))
    except ValueError:
        return [_semantic_value_issue("unsupported_attribute_operator", context.plan.action)]
    return []


@register_semantic_validation_rule("attribute_value_requirement", "extract_by_attribute")
def _validate_attribute_value_requirement(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if "operator" not in context.action_input:
        return []
    try:
        operator = _attribute_operator(context.action_input.get("operator"))
    except ValueError:
        return []
    if operator in {8, 9}:  # is_null / is_not_null
        return []
    value = context.action_input.get("value")
    if value is None or str(value).strip() == "":
        params = {"action": context.plan.action, "missing_slots": ["value"]}
        return [
            ValidationIssue(
                code="missing_slot",
                stage="semantic",
                severity="error",
                message_key="semantic.missing_slots",
                params=params,
                repair=RepairProposal(kind="ask_user", message_key="semantic.missing_slots", params=params),
            )
        ]
    return []


@register_semantic_validation_rule("spatial_predicate", "extract_by_location", "join_by_location")
def _validate_spatial_predicate(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if "predicate" not in context.action_input:
        return []
    try:
        _spatial_predicates(context.action_input.get("predicate"))
    except ValueError:
        return [_semantic_value_issue("unsupported_spatial_predicate", context.plan.action)]
    return []


@register_semantic_validation_rule("field_type", "field_calculator")
def _validate_field_type(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if "field_type" not in context.action_input:
        return []
    try:
        _field_type(context.action_input.get("field_type"))
    except ValueError:
        return [_semantic_value_issue("unsupported_field_type", context.plan.action)]
    return []


def _distance_to_meters(value: Any, unit: Any = "") -> float:
    unit_text = str(unit or "").strip().lower()
    raw_text = str(value or "").strip().lower()
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z\u4e00-\u9fff]*)", raw_text)
    if match:
        distance = float(match.group(1))
        if not unit_text:
            unit_text = match.group(2).strip().lower()
    else:
        try:
            distance = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_distance") from exc

    if distance <= 0:
        raise ValueError("invalid_distance")

    if unit_text in {"", "m", "meter", "meters", "metre", "metres", "米"}:
        return distance
    if unit_text in {"km", "kilometer", "kilometers", "kilometre", "kilometres", "公里", "千米"}:
        return distance * 1000.0
    raise ValueError("unsupported_unit")


def _semantic_value_issue(code: str, action: str) -> ValidationIssue:
    params = {"action": action}
    return ValidationIssue(
        code=code,
        stage="semantic",
        severity="error",
        message_key=f"semantic.{code}",
        params=params,
        repair=RepairProposal(kind="ask_user", message_key=f"semantic.{code}", params=params),
    )


def _distance_in_map_units(value: Any, unit: Any = "") -> float:
    return _distance_to_meters(value, unit)


def _attribute_operator(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = str(value or "").strip().lower()
    mapping = {
        "=": 0,
        "==": 0,
        "eq": 0,
        "equals": 0,
        "equal": 0,
        "!=": 1,
        "<>": 1,
        "ne": 1,
        "not_equal": 1,
        ">": 2,
        "gt": 2,
        ">=": 3,
        "gte": 3,
        "<": 4,
        "lt": 4,
        "<=": 5,
        "lte": 5,
        "begins_with": 6,
        "starts_with": 6,
        "contains": 7,
        "is_null": 8,
        "is_not_null": 9,
        "does_not_contain": 10,
    }
    if text not in mapping:
        raise ValueError("unsupported_attribute_operator")
    return mapping[text]


def _spatial_predicates(value: Any) -> list[int]:
    raw_values = value if isinstance(value, list) else [value]
    predicates: list[int] = []
    mapping = {
        "intersect": 0,
        "intersects": 0,
        "contain": 1,
        "contains": 1,
        "disjoint": 2,
        "equal": 3,
        "equals": 3,
        "touch": 4,
        "touches": 4,
        "overlap": 5,
        "overlaps": 5,
        "within": 6,
        "cross": 7,
        "crosses": 7,
    }
    for item in raw_values:
        if isinstance(item, int):
            predicates.append(item)
            continue
        text = str(item or "").strip().lower()
        if text not in mapping:
            raise ValueError("unsupported_spatial_predicate")
        predicates.append(mapping[text])
    return predicates or [0]


def _field_type(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = str(value or "float").strip().lower()
    mapping = {
        "float": 0,
        "double": 0,
        "decimal": 0,
        "integer": 1,
        "int": 1,
        "string": 2,
        "text": 2,
        "date": 3,
    }
    if text not in mapping:
        raise ValueError("unsupported_field_type")
    return mapping[text]
