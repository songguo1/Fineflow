"""Persistent artifact index for PineFlow workspace sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext, safe_workspace_name
from pineflow_agent.policies.output_policy import is_materialized_output, is_reusable_output, needs_disk_output
from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action

ArtifactRole = Literal["input", "intermediate", "final", "report"]
ArtifactKind = Literal["vector", "raster", "table", "report", "unknown"]


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    role: ArtifactRole
    kind: ArtifactKind
    name: str
    path: str
    layer_id: str = ""
    algorithm_id: str = ""
    crs: str = ""
    geometry_type: str = ""
    feature_count: Any = None
    fields: list[Any] = field(default_factory=list)
    extent: Any = None
    parent_ids: list[str] = field(default_factory=list)
    input_layer_ids: list[str] = field(default_factory=list)
    input_layer_names: list[str] = field(default_factory=list)
    input_artifact_ids: list[str] = field(default_factory=list)
    input_artifacts: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    source_run_id: str = ""
    source_action: str = ""
    source_step: int | None = None
    created_at: str = ""
    exists: bool = False
    materialized: bool = True
    reusable: bool = True
    expires_at: str = ""
    quality_flags: list[Any] = field(default_factory=list)

    @classmethod
    def from_layer(
        cls,
        layer: dict[str, Any],
        *,
        role: ArtifactRole,
        source_step: int | None = None,
        artifact_id: str = "",
        created_at: str = "",
    ) -> "ArtifactRecord":
        metadata = dict(layer.get("metadata") or {})
        input_artifacts = _input_artifacts_for_layer(layer)
        input_artifact_ids = _input_artifact_ids_for_layer(layer, input_artifacts=input_artifacts)
        lineage = _lineage_for_layer(
            layer,
            input_artifacts=input_artifacts,
            input_artifact_ids=input_artifact_ids,
            source_step=source_step,
        )
        input_layer_names = [str(item) for item in list(lineage.get("input_layer_names") or []) if str(item or "").strip()]
        return cls(
            artifact_id=artifact_id or _new_artifact_id(layer),
            role=role,
            kind=_artifact_kind(str(layer.get("kind") or "")),
            name=str(layer.get("name") or ""),
            path=str(layer.get("source") or ""),
            layer_id=str(layer.get("layer_id") or ""),
            algorithm_id=str(layer.get("algorithm_id") or ""),
            crs=str(metadata.get("crs") or ""),
            geometry_type=str(metadata.get("geometry_type") or ""),
            feature_count=metadata.get("feature_count"),
            fields=list(metadata.get("fields") or []),
            extent=metadata.get("extent") or metadata.get("bounds"),
            parent_ids=[str(item) for item in list(layer.get("parent_ids") or [])],
            input_layer_ids=[str(item) for item in list(lineage.get("input_layer_ids") or []) if str(item or "").strip()],
            input_layer_names=input_layer_names,
            input_artifact_ids=input_artifact_ids,
            input_artifacts=input_artifacts,
            parameters=make_json_safe(dict(layer.get("parameters") or {})),
            lineage=lineage,
            source_run_id=str(lineage.get("source_run_id") or ""),
            source_action=str(lineage.get("source_action") or ""),
            source_step=source_step,
            created_at=created_at or _utc_now(),
            exists=_path_exists(str(layer.get("source") or "")),
            materialized=_is_materialized(str(layer.get("source") or "")),
            reusable=_is_reusable(str(layer.get("source") or ""), role),
            quality_flags=list(metadata.get("quality_flags") or metadata.get("warnings") or []),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactRecord":
        path = str(payload.get("path") or "")
        role = _artifact_role(str(payload.get("role") or ""))
        return cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            role=role,
            kind=_artifact_kind(str(payload.get("kind") or "")),
            name=str(payload.get("name") or ""),
            path=path,
            layer_id=str(payload.get("layer_id") or ""),
            algorithm_id=str(payload.get("algorithm_id") or ""),
            crs=str(payload.get("crs") or ""),
            geometry_type=str(payload.get("geometry_type") or ""),
            feature_count=payload.get("feature_count"),
            fields=list(payload.get("fields") or []),
            extent=payload.get("extent"),
            parent_ids=[str(item) for item in list(payload.get("parent_ids") or [])],
            input_layer_ids=[
                str(item)
                for item in list(payload.get("input_layer_ids") or dict(payload.get("lineage") or {}).get("input_layer_ids") or [])
                if str(item or "").strip()
            ],
            input_layer_names=[
                str(item)
                for item in list(payload.get("input_layer_names") or dict(payload.get("lineage") or {}).get("input_layer_names") or [])
                if str(item or "").strip()
            ],
            input_artifact_ids=[str(item) for item in list(payload.get("input_artifact_ids") or []) if str(item or "").strip()],
            input_artifacts=_input_artifacts_for_layer(payload),
            parameters=make_json_safe(dict(payload.get("parameters") or {})),
            lineage=make_json_safe(dict(payload.get("lineage") or {})),
            source_run_id=str(payload.get("source_run_id") or dict(payload.get("lineage") or {}).get("source_run_id") or ""),
            source_action=str(payload.get("source_action") or dict(payload.get("lineage") or {}).get("source_action") or payload.get("algorithm_id") or ""),
            source_step=int(payload["source_step"]) if payload.get("source_step") is not None else None,
            created_at=str(payload.get("created_at") or ""),
            exists=bool(payload["exists"]) if "exists" in payload else _path_exists(path),
            materialized=bool(payload["materialized"]) if "materialized" in payload else _is_materialized(path),
            reusable=bool(payload["reusable"]) if "reusable" in payload else _is_reusable(path, role),
            expires_at=str(payload.get("expires_at") or ""),
            quality_flags=list(payload.get("quality_flags") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(
            {
                "artifact_id": self.artifact_id,
                "role": self.role,
                "kind": self.kind,
                "name": self.name,
                "path": self.path,
                "layer_id": self.layer_id,
                "algorithm_id": self.algorithm_id,
                "crs": self.crs,
                "geometry_type": self.geometry_type,
                "feature_count": self.feature_count,
                "fields": list(self.fields),
                "extent": make_json_safe(self.extent),
                "parent_ids": list(self.parent_ids),
                "input_layer_ids": list(self.input_layer_ids),
                "input_layer_names": list(self.input_layer_names),
                "input_artifact_ids": list(self.input_artifact_ids),
                "input_artifacts": make_json_safe(list(self.input_artifacts)),
                "parameters": make_json_safe(self.parameters),
                "lineage": make_json_safe(self.lineage),
                "source_run_id": self.source_run_id,
                "source_action": self.source_action,
                "source_step": self.source_step,
                "created_at": self.created_at,
                "exists": self.exists,
                "materialized": self.materialized,
                "reusable": self.reusable,
                "expires_at": self.expires_at,
                "quality_flags": make_json_safe(list(self.quality_flags)),
            }
        )

    def output_dict(self) -> dict[str, Any]:
        display_title = _artifact_display_title(self)
        display_summary = _artifact_display_summary(self)
        return make_json_safe(
            {
                "artifact_id": self.artifact_id,
                "role": self.role,
                "layer_id": self.layer_id,
                "name": self.name,
                "path": self.path,
                "kind": self.kind,
                "algorithm_id": self.algorithm_id,
                "crs": self.crs,
                "geometry_type": self.geometry_type,
                "feature_count": self.feature_count,
                "fields": list(self.fields),
                "extent": make_json_safe(self.extent),
                "parent_ids": list(self.parent_ids),
                "input_layer_ids": list(self.input_layer_ids),
                "input_layer_names": list(self.input_layer_names),
                "input_artifact_ids": list(self.input_artifact_ids),
                "input_artifacts": make_json_safe(list(self.input_artifacts)),
                "parameters": make_json_safe(self.parameters),
                "lineage": make_json_safe(self.lineage),
                "source_run_id": self.source_run_id,
                "source_action": self.source_action,
                "source_step": self.source_step,
                "exists": self.exists,
                "materialized": self.materialized,
                "reusable": self.reusable,
                "quality_flags": make_json_safe(list(self.quality_flags)),
                "file_name": Path(self.path).name if self.path else "",
                "display_title": display_title,
                "display_summary": display_summary,
                "summary_lines": _artifact_summary_lines(self, display_summary=display_summary),
            }
        )


class ArtifactIndex:
    """Small append/update index stored as artifacts.json in a session workspace."""

    def __init__(self, *, path: str | Path, records: list[ArtifactRecord] | None = None) -> None:
        self.path = Path(path)
        self.records = list(records or [])

    @classmethod
    def for_workspace(cls, workspace: WorkspaceContext) -> "ArtifactIndex":
        return cls.load(workspace.artifacts_index_path)

    @classmethod
    def load(cls, path: str | Path) -> "ArtifactIndex":
        index_path = Path(path)
        if not index_path.exists():
            return cls(path=index_path)
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(path=index_path)
        items = payload.get("artifacts") if isinstance(payload, dict) else []
        records = [
            ArtifactRecord.from_dict(dict(item))
            for item in list(items or [])
            if isinstance(item, dict)
        ]
        return cls(path=index_path, records=records)

    def register_layer(
        self,
        layer: dict[str, Any],
        *,
        role: ArtifactRole,
        source_step: int | None = None,
        source_run_id: str = "",
        source_action: str = "",
    ) -> ArtifactRecord:
        layer_payload = self._layer_with_input_artifacts(layer)
        layer_payload = _layer_with_source_context(
            layer_payload,
            source_run_id=source_run_id,
            source_action=source_action,
            source_step=source_step,
        )
        record = ArtifactRecord.from_layer(
            layer_payload,
            role=role,
            source_step=source_step,
            artifact_id=self._existing_artifact_id(layer_payload, role=role),
            created_at=self._existing_created_at(layer_payload, role=role),
        )
        self._upsert(record)
        self.save()
        return record

    def find_record(
        self,
        *,
        artifact_id: str = "",
        layer_id: str = "",
        path: str = "",
        role: str = "",
    ) -> ArtifactRecord | None:
        normalized_path = _normalized_path(path)
        requested_role = str(role or "").strip().lower()
        requested_artifact_id = str(artifact_id or "").strip()
        requested_layer_id = str(layer_id or "").strip()
        for record in reversed(self.records):
            if requested_role and record.role != requested_role:
                continue
            if requested_artifact_id and record.artifact_id == requested_artifact_id:
                return record
            if requested_layer_id and record.layer_id == requested_layer_id:
                if not normalized_path or _normalized_path(record.path) == normalized_path:
                    return record
            if normalized_path and _normalized_path(record.path) == normalized_path:
                return record
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": _utc_now(),
            "artifacts": [record.to_dict() for record in self.records],
        }

    def outputs(
        self,
        *,
        include_inputs: bool = False,
        include_intermediate: bool = False,
    ) -> list[dict[str, Any]]:
        roles: set[str] = {"final", "report"}
        if include_intermediate:
            roles.add("intermediate")
        if include_inputs:
            roles.add("input")
        return [record.output_dict() for record in self.records if record.role in roles and record.path]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _upsert(self, record: ArtifactRecord) -> None:
        key = _record_key(record)
        for index, existing in enumerate(self.records):
            if _record_key(existing) == key:
                self.records[index] = record
                return
        self.records.append(record)

    def _existing_artifact_id(self, layer: dict[str, Any], *, role: ArtifactRole) -> str:
        key = _layer_key(layer, role=role)
        for record in self.records:
            if _record_key(record) == key:
                return record.artifact_id
        return ""

    def _existing_created_at(self, layer: dict[str, Any], *, role: ArtifactRole) -> str:
        key = _layer_key(layer, role=role)
        for record in self.records:
            if _record_key(record) == key:
                return record.created_at
        return ""

    def _layer_with_input_artifacts(self, layer: dict[str, Any]) -> dict[str, Any]:
        payload = make_json_safe(dict(layer or {}))
        if payload.get("input_artifacts"):
            return payload
        input_artifacts: list[dict[str, Any]] = []
        for parent_id in [str(item) for item in list(payload.get("parent_ids") or []) if str(item or "").strip()]:
            record = self.find_record(layer_id=parent_id)
            if record is None:
                continue
            input_artifacts.append(_artifact_ref(record))
        if not input_artifacts:
            return payload
        payload["input_artifacts"] = make_json_safe(input_artifacts)
        payload["input_artifact_ids"] = [
            str(item.get("artifact_id") or "")
            for item in input_artifacts
            if str(item.get("artifact_id") or "").strip()
        ]
        return payload


def _record_key(record: ArtifactRecord) -> tuple[str, str, str]:
    return (record.role, _normalized_path(record.path), record.layer_id)


def _layer_key(layer: dict[str, Any], *, role: ArtifactRole) -> tuple[str, str, str]:
    path = str(layer.get("source") or "")
    return (role, _normalized_path(path), str(layer.get("layer_id") or ""))


def _layer_with_source_context(
    layer: dict[str, Any],
    *,
    source_run_id: str = "",
    source_action: str = "",
    source_step: int | None = None,
) -> dict[str, Any]:
    payload = make_json_safe(dict(layer or {}))
    metadata = dict(payload.get("metadata") or {})
    lineage = dict(payload.get("lineage") or metadata.get("lineage") or {})
    if source_run_id:
        payload["source_run_id"] = source_run_id
        metadata["source_run_id"] = source_run_id
        lineage["source_run_id"] = source_run_id
    if source_action:
        payload["source_action"] = source_action
        metadata["source_action"] = source_action
        lineage["source_action"] = source_action
    if source_step is not None:
        payload["source_step"] = source_step
        metadata["source_step"] = source_step
        lineage["source_step"] = source_step
    if lineage:
        payload["lineage"] = lineage
        metadata["lineage"] = lineage
    if metadata:
        payload["metadata"] = metadata
    return payload


def _new_artifact_id(layer: dict[str, Any]) -> str:
    base = safe_workspace_name(str(layer.get("name") or layer.get("layer_id") or "artifact"))
    return f"{base}_{uuid4().hex[:8]}"


def _artifact_role(value: str) -> ArtifactRole:
    return value if value in {"input", "intermediate", "final", "report"} else "intermediate"


def _artifact_kind(value: str) -> ArtifactKind:
    return value if value in {"vector", "raster", "table", "report"} else "unknown"


def _lineage_for_layer(
    layer: dict[str, Any],
    *,
    input_artifacts: list[dict[str, Any]] | None = None,
    input_artifact_ids: list[str] | None = None,
    source_step: int | None = None,
) -> dict[str, Any]:
    lineage = dict(layer.get("lineage") or {})
    metadata = dict(layer.get("metadata") or {})
    if not lineage and isinstance(metadata.get("lineage"), dict):
        lineage = dict(metadata.get("lineage") or {})
    resolved_input_artifacts = list(input_artifacts or _input_artifacts_for_layer(layer))
    resolved_input_ids = list(input_artifact_ids or _input_artifact_ids_for_layer(layer, input_artifacts=resolved_input_artifacts))
    input_layer_names = _input_layer_names_for_layer(layer, input_artifacts=resolved_input_artifacts)
    input_layer_ids = [str(item) for item in list(layer.get("parent_ids") or lineage.get("input_layer_ids") or []) if str(item or "").strip()]
    source_action = str(layer.get("source_action") or metadata.get("source_action") or lineage.get("source_action") or layer.get("algorithm_id") or "").strip()
    source_run_id = str(layer.get("source_run_id") or metadata.get("source_run_id") or lineage.get("source_run_id") or "").strip()
    resolved_source_step = layer.get("source_step", metadata.get("source_step", lineage.get("source_step", source_step)))
    return make_json_safe(
        {
            "operation": str(layer.get("algorithm_id") or lineage.get("operation") or ""),
            "source_action": source_action,
            "source_run_id": source_run_id,
            "source_step": resolved_source_step,
            "input_layer_ids": input_layer_ids,
            "input_layer_names": input_layer_names,
            "input_artifact_ids": resolved_input_ids,
            "input_artifacts": make_json_safe(resolved_input_artifacts),
            "parameters": dict(layer.get("parameters") or lineage.get("parameters") or {}),
        }
    )


def _artifact_display_title(record: ArtifactRecord) -> str:
    if record.role == "report":
        return "最终报告"
    if record.algorithm_id == "export_result":
        return "导出结果"
    source_title = _artifact_source_title(record)
    if source_title and source_title != (record.algorithm_id or ""):
        return source_title if source_title.endswith("结果") else f"{source_title}结果"
    return {
        "input": "输入数据",
        "intermediate": "中间结果",
        "final": "最终结果",
    }.get(record.role, "结果")


def _artifact_display_summary(record: ArtifactRecord) -> str:
    name = record.name or record.layer_id or record.artifact_id or "结果"
    file_name = Path(record.path).name if record.path else ""
    count_text = _artifact_count_text(record)
    geometry = str(record.geometry_type or "").strip()
    crs = str(record.crs or "").strip()
    action_label = _artifact_source_title(record)
    semantic_name = _artifact_semantic_name(record)

    if record.role == "report":
        return f"已生成最终报告 {file_name or name}。"
    if str(record.algorithm_id or "").strip() == "export_result":
        count_suffix = f"（{count_text}）" if count_text else ""
        target = file_name or record.path or name
        source_name = semantic_name or name
        return f"已导出 {source_name}{count_suffix} 到 {target}。"
    if action_label:
        details = _join_artifact_details(count_text, geometry, crs)
        suffix = f"，{details}" if details else ""
        label = semantic_name or name
        return f"{label}：{action_label}{suffix}。"
    generic_label = _artifact_kind_label(record.kind)
    details = _join_artifact_details(count_text, geometry, crs)
    suffix = f"，{details}" if details else ""
    return f"{name}：{generic_label}产物{suffix}。"


def _artifact_summary_lines(record: ArtifactRecord, *, display_summary: str) -> list[str]:
    lines: list[str] = []
    if display_summary:
        lines.append(display_summary)
    source_title = _artifact_source_title(record)
    if source_title:
        lines.append(f"来源：{source_title}")
    if record.source_step is not None:
        lines.append(f"步骤：第 {record.source_step} 步")
    input_names = _artifact_input_names(record)
    if input_names:
        lines.append(f"输入：{', '.join(input_names[:3])}")
    if record.path:
        lines.append(f"文件：{Path(record.path).name}")
    if record.reusable:
        lines.append("可复用：是")
    return lines


def _artifact_action_label(algorithm_id: str) -> str:
    if not algorithm_id:
        return ""
    title = display_title_for_action(algorithm_id)
    if title and title != algorithm_id:
        return title
    return {
        "native:buffer": "缓冲区分析",
        "native:extractbyattribute": "按属性筛选",
        "native:extractbylocation": "按位置筛选",
        "native:joinattributesbylocation": "空间连接",
        "native:joinbynearest": "最近邻连接",
        "native:countpointsinpolygon": "面内点计数",
        "export_result": "导出结果",
    }.get(algorithm_id, "")


def _artifact_source_title(record: ArtifactRecord) -> str:
    source_action = str(record.source_action or record.lineage.get("source_action") or "").strip()
    if source_action:
        title = display_title_for_action(source_action)
        if title and title != source_action:
            return title
    return _artifact_action_label(str(record.algorithm_id or "").strip())


def _artifact_count_text(record: ArtifactRecord) -> str:
    if record.feature_count is None:
        return ""
    unit = "行" if record.kind == "table" else "要素"
    return f"{record.feature_count} {unit}"


def _artifact_semantic_name(record: ArtifactRecord) -> str:
    source_action = str(record.source_action or record.lineage.get("source_action") or "").strip().lower()
    parameters = dict(record.parameters or record.lineage.get("parameters") or {})
    input_names = _artifact_input_names(record)
    primary = input_names[0] if input_names else ""
    secondary = input_names[1] if len(input_names) > 1 else ""

    if source_action == "buffer_layer":
        distance = _artifact_parameter_text(parameters, "distance", "DISTANCE")
        if primary and distance:
            return f"{primary} {distance}缓冲区"
        if primary:
            return f"{primary}缓冲区"
    if source_action == "csv_to_points" and primary:
        return f"{primary}转点结果"
    if source_action == "extract_by_location":
        if primary and secondary:
            return f"{primary}与{secondary}按位置筛选结果"
        if primary:
            return f"{primary}按位置筛选结果"
    if source_action == "clip_layer":
        if primary and secondary:
            return f"{primary}按{secondary}裁剪结果"
        if primary:
            return f"{primary}裁剪结果"
    if source_action == "intersect_layer":
        if primary and secondary:
            return f"{primary}与{secondary}叠置结果"
        if primary:
            return f"{primary}叠置结果"
    if source_action == "select_by_expression" and primary:
        return f"{primary}属性筛选结果"
    if source_action == "keep_fields" and primary:
        return f"{primary}字段整理结果"
    if source_action == "rename_field" and primary:
        return f"{primary}字段重命名结果"
    if source_action == "field_calculator" and primary:
        return f"{primary}字段计算结果"
    if str(record.algorithm_id or "").strip().lower() == "export_result" and primary:
        return primary
    return ""


def _artifact_kind_label(kind: str) -> str:
    return {
        "vector": "矢量",
        "raster": "栅格",
        "table": "表格",
        "report": "报告",
    }.get(str(kind or "").strip(), "结果")


def _join_artifact_details(*parts: str) -> str:
    return "，".join(part for part in parts if str(part or "").strip())


def _artifact_parameter_text(parameters: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = parameters.get(key)
        if value is None or value == "":
            continue
        text = str(value).strip()
        if not text:
            continue
        lowered = text.lower()
        if any(unit in lowered for unit in ("m", "km", "米", "公里")):
            return text
        return f"{text}m"
    return ""


def _input_artifacts_for_layer(layer: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = dict(layer.get("metadata") or {})
    lineage = dict(layer.get("lineage") or {})
    if not lineage and isinstance(metadata.get("lineage"), dict):
        lineage = dict(metadata.get("lineage") or {})
    candidates = (
        layer.get("input_artifacts")
        or metadata.get("input_artifacts")
        or lineage.get("input_artifacts")
        or []
    )
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in list(candidates or []):
        if not isinstance(item, dict):
            continue
        payload = make_json_safe(dict(item))
        key = (
            str(payload.get("artifact_id") or ""),
            str(payload.get("layer_id") or ""),
            _normalized_path(str(payload.get("path") or "")),
        )
        if key in seen:
            continue
        seen.add(key)
        results.append(payload)
    return results


def _input_artifact_ids_for_layer(
    layer: dict[str, Any],
    *,
    input_artifacts: list[dict[str, Any]] | None = None,
) -> list[str]:
    metadata = dict(layer.get("metadata") or {})
    lineage = dict(layer.get("lineage") or {})
    if not lineage and isinstance(metadata.get("lineage"), dict):
        lineage = dict(metadata.get("lineage") or {})
    direct = list(layer.get("input_artifact_ids") or metadata.get("input_artifact_ids") or lineage.get("input_artifact_ids") or [])
    ids = [str(item) for item in direct if str(item or "").strip()]
    if ids:
        return list(dict.fromkeys(ids))
    resolved: list[str] = []
    for item in list(input_artifacts or _input_artifacts_for_layer(layer)):
        artifact_id = str(item.get("artifact_id") or "").strip()
        if artifact_id:
            resolved.append(artifact_id)
    return list(dict.fromkeys(resolved))


def _input_layer_names_for_layer(
    layer: dict[str, Any],
    *,
    input_artifacts: list[dict[str, Any]] | None = None,
) -> list[str]:
    names: list[str] = []
    for item in list(input_artifacts or _input_artifacts_for_layer(layer)):
        label = str(item.get("name") or item.get("layer_id") or item.get("artifact_id") or "").strip()
        if label:
            names.append(label)
    if names:
        return list(dict.fromkeys(names))
    return [str(item) for item in list(layer.get("parent_ids") or []) if str(item or "").strip()]


def _artifact_ref(record: ArtifactRecord) -> dict[str, Any]:
    payload = record.output_dict()
    return make_json_safe(
        {
            "artifact_id": payload.get("artifact_id"),
            "layer_id": payload.get("layer_id"),
            "name": payload.get("name"),
            "role": payload.get("role"),
            "kind": payload.get("kind"),
            "path": payload.get("path"),
            "file_name": payload.get("file_name"),
            "display_title": payload.get("display_title"),
            "display_summary": payload.get("display_summary"),
            "source_step": payload.get("source_step"),
            "source_run_id": payload.get("source_run_id"),
            "source_action": payload.get("source_action"),
            "algorithm_id": payload.get("algorithm_id"),
            "crs": payload.get("crs"),
            "geometry_type": payload.get("geometry_type"),
            "feature_count": payload.get("feature_count"),
            "input_layer_names": payload.get("input_layer_names"),
            "input_artifact_ids": payload.get("input_artifact_ids"),
            "parameters": payload.get("parameters"),
            "reusable": payload.get("reusable"),
        }
    )


def _artifact_input_names(record: ArtifactRecord) -> list[str]:
    names: list[str] = []
    for item in list(record.input_artifacts or []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("name") or item.get("layer_id") or item.get("artifact_id") or "").strip()
        if label:
            names.append(label)
    if names:
        return list(dict.fromkeys(names))
    if record.input_layer_names:
        names.extend(str(item) for item in list(record.input_layer_names) if str(item or "").strip())
        if names:
            return list(dict.fromkeys(names))
    return [str(item) for item in list(record.parent_ids or []) if str(item or "").strip()]


def _path_exists(path: str) -> bool:
    if not path or needs_disk_output(path):
        return False
    try:
        return Path(path).exists()
    except (OSError, ValueError):
        return False


def _is_materialized(path: str) -> bool:
    return is_materialized_output(path)


def _is_reusable(path: str, role: ArtifactRole) -> bool:
    return is_reusable_output(path, role)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _normalized_path(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve()).lower()
    except (OSError, ValueError):
        return str(path).strip().lower()
