"""QGIS toolbox: discovery, data loading, standard calls, and exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pineflow_runtime.errors import QGISRuntimeError, ToolExecutionError, ToolValidationError
from pineflow_runtime.runtime import QGISRuntime, csv_uri_for_path, driver_for_vector_path

from pineflow_agent.core.artifacts import ArtifactRole
from pineflow_agent.core.field_metadata import field_records
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.models import Observation
from pineflow_agent.core.state_tree import GISStateTree, LayerRecord
from pineflow_agent.core.workspace import WorkspaceContext
from pineflow_agent.tools.qgis.artifact_recorder import QGISArtifactRecorder
from pineflow_agent.tools.qgis.data_source_inspector import QGISDataSourceInspector
from pineflow_agent.tools.qgis.layer_registrar import QGISLayerRegistrar
from pineflow_agent.tools.qgis.metadata_normalizer import QGISMetadataNormalizer
from pineflow_agent.tools.qgis.output_resolver import QGISOutputResolver
from pineflow_agent.tools.qgis.processing_output_handler import QGISProcessingOutputHandler

PROCESSING_LAYER_REF_KEYS = {
    "INPUT",
    "INPUT_LAYER",
    "INPUT_RASTER",
    "INPUT_2",
    "LAYERS",
    "OVERLAY",
    "INTERSECT",
    "JOIN",
    "REFERENCE_LAYER",
    "POLYGONS",
    "POINTS",
    "MASK",
    "RASTERCOPY",
    "TABLE",
}


class QGISToolbox:
    """Thin, explicit toolbox around PyQGIS processing APIs."""

    def __init__(
        self,
        *,
        runtime: QGISRuntime | None = None,
        state: GISStateTree | None = None,
        session_id: str = "",
        workspace: WorkspaceContext | None = None,
    ) -> None:
        self.runtime = runtime or QGISRuntime()
        self.state = state or GISStateTree()
        base = workspace or WorkspaceContext()
        self.workspace = base.with_session(session_id or base.session_id or "default")
        self.session_id = self.workspace.session_id
        self.output_resolver = QGISOutputResolver(self.workspace)
        self.artifact_recorder = QGISArtifactRecorder(self.workspace)
        self.data_sources = QGISDataSourceInspector()
        self.metadata_normalizer = QGISMetadataNormalizer(self.runtime)
        self.processing_outputs = QGISProcessingOutputHandler(self.output_resolver)
        self.layer_registrar = QGISLayerRegistrar(self.state, self.artifact_recorder)
        self.artifacts = self.artifact_recorder.artifacts

    def set_session_id(self, session_id: str) -> None:
        self.workspace = self.workspace.with_session(session_id or "default")
        self.session_id = self.workspace.session_id
        self.output_resolver.set_workspace(self.workspace)
        self.artifact_recorder.set_workspace(self.workspace)
        self.artifacts = self.artifact_recorder.artifacts

    def discover_algorithms(self, query: str = "", *, limit: int = 30) -> list[dict[str, Any]]:
        """Return QGIS processing algorithms the LLM can choose from."""
        return self.runtime.list_algorithms(query, limit=limit)

    def algorithm_help(self, algorithm_id: str) -> dict[str, Any]:
        """Return parameter requirements similar to processing.algorithmHelp()."""
        try:
            return self.runtime.algorithm_help(algorithm_id)
        except Exception as exc:
            raise ToolValidationError(str(exc)) from exc

    def load_vector(self, input_path: str, *, name: str = "") -> Observation:
        try:
            path = self._existing_path(input_path)
            metadata = make_json_safe(self.runtime.inspect_vector_path(path))
            record = self.layer_registrar.register(
                name=name or Path(path).stem,
                kind="vector",
                source=path,
                role="input",
                source_action="load_vector",
                metadata=metadata,
            )
            return self.layer_registrar.success_observation(
                record,
                message=f"Loaded vector layer {record.name}.",
                data={"layer": record.to_dict()},
            )
        except Exception as exc:
            return self._error_observation(exc)

    def load_raster(self, input_path: str, *, name: str = "") -> Observation:
        try:
            path = self._existing_path(input_path)
            metadata = make_json_safe(self.runtime.inspect_raster_path(path))
            record = self.layer_registrar.register(
                name=name or Path(path).stem,
                kind="raster",
                source=path,
                role="input",
                source_action="load_raster",
                metadata=metadata,
            )
            return self.layer_registrar.success_observation(
                record,
                message=f"Loaded raster layer {record.name}.",
                data={"layer": record.to_dict()},
            )
        except Exception as exc:
            return self._error_observation(exc)

    def load_csv(self, input_path: str, *, name: str = "") -> Observation:
        try:
            path = self._existing_path(input_path)
            metadata = self._inspect_csv(path)
            metadata["source_uri"] = csv_uri_for_path(path, encoding=str(metadata.get("encoding") or ""))
            diagnostics = self._csv_field_diagnostics(list(metadata.get("fields") or []))
            metadata.update(diagnostics)
            record = self.layer_registrar.register(
                name=name or Path(path).stem,
                kind="table",
                source=path,
                role="input",
                source_action="load_csv",
                metadata=metadata,
            )
            message = f"Loaded CSV table {record.name}."
            if metadata.get("suspected_encoding_issue"):
                message += " Field names look garbled; verify the CSV encoding before running downstream GIS tools."
            return self.layer_registrar.success_observation(
                record,
                message=message,
                data={"layer": record.to_dict()},
            )
        except Exception as exc:
            return self._error_observation(exc)

    def csv_to_points(
        self,
        input_ref: str,
        *,
        x_field: str,
        y_field: str,
        crs: str = "EPSG:4326",
        output_name: str = "",
        output_path: str = "",
    ) -> Observation:
        self._begin_output_path_tracking()
        try:
            record = self.state.resolve(input_ref)
            if record.kind != "table":
                raise ToolValidationError("csv_to_points requires a loaded CSV table.")
            available_fields = [str(field) for field in list(record.metadata.get("fields") or [])]
            if x_field not in available_fields or y_field not in available_fields:
                raise ToolValidationError(
                    "CSV coordinate fields were not found in the loaded table. "
                    f"Requested x={x_field}, y={y_field}. Available fields: {', '.join(available_fields) or '<none>'}."
                )
            if self._needs_disk_output(output_path):
                output = self._next_temp_output_path(
                    "native:createpointslayerfromtable",
                    output_name=output_name or f"{record.name}_points",
                )
            else:
                output = output_path
            metadata = make_json_safe(
                self.runtime.csv_to_points(
                    record.source,
                    x_field=x_field,
                    y_field=y_field,
                    crs_authid=crs or "EPSG:4326",
                    encoding=str(record.metadata.get("encoding") or ""),
                    output_path=output,
                )
            )
            metadata = self._metadata_with_fallback_crs(metadata, crs or "EPSG:4326")
            exported = self.layer_registrar.register(
                name=output_name or f"{record.name}_points",
                kind="vector",
                source=output,
                role="intermediate",
                parent_ids=[record.layer_id],
                algorithm_id="csv_to_points",
                parameters={"input_ref": input_ref, "x_field": x_field, "y_field": y_field, "crs": crs},
                metadata=metadata,
            )
            return self.layer_registrar.success_observation(
                exported,
                message=f"Created point layer {exported.name} from CSV.",
                data=self._with_output_path_warnings({"layer": exported.to_dict()}),
            )
        except Exception as exc:
            return self._error_observation(exc)

    def summarize_layer(self, layer_ref: str, *, detail_level: str = "summary") -> Observation:
        try:
            record = self.state.resolve(layer_ref)
            summary = _layer_summary(record, detail_level=detail_level)
            return Observation(
                status="success",
                message=f"Summarized layer {record.name}.",
                output_layer_id=record.layer_id,
                output_path=record.source,
                data={
                    "summary": summary,
                    "markdown": _layer_summary_markdown(summary),
                },
            )
        except Exception as exc:
            return self._error_observation(exc)

    def run_algorithm(self, algorithm_id: str, parameters: dict[str, Any], *, output_name: str = "") -> Observation:
        """Standard processing.run() wrapper with layer-ref normalization."""
        self._begin_output_path_tracking()
        try:
            normalized = self._normalize_processing_parameters(parameters)
            normalized = self._ensure_disk_backed_outputs(
                algorithm_id,
                normalized,
                output_name=output_name,
            )
            result = self.runtime.run_algorithm(algorithm_id, normalized)
            output_path = self._extract_output_path(result, normalized)
            parent_ids = self._collect_parent_ids(parameters)
            metadata = make_json_safe(self._metadata_for_output(output_path))
            record = self.layer_registrar.register(
                name=output_name or self._derive_output_name(algorithm_id, output_path),
                kind=self._kind_from_output(output_path),
                source=output_path,
                role="intermediate",
                parent_ids=parent_ids,
                algorithm_id=algorithm_id,
                parameters=make_json_safe(normalized),
                metadata=metadata,
            )
            return self.layer_registrar.success_observation(
                record,
                message=f"Executed {algorithm_id}.",
                data=self._with_output_path_warnings({"qgis_result": make_json_safe(result), "layer": record.to_dict()}),
            )
        except Exception as exc:
            return self._error_observation(exc)

    def export_result(self, layer_ref: str, output_path: str) -> Observation:
        try:
            record = self.state.resolve(layer_ref)
            if record.kind == "vector":
                output_path = self._normalize_export_path(output_path, default_stem=record.name)
                driver = driver_for_vector_path(output_path)
                metadata = make_json_safe(self.runtime.write_vector(record.source, output_path, driver_name=driver))
                parameters = {"output_path": output_path, "driver": driver}
            elif record.kind == "raster":
                output_path = self._normalize_raster_export_path(output_path, default_stem=record.name)
                result = self.runtime.run_algorithm("gdal:translate", {"INPUT": record.source, "OUTPUT": output_path})
                metadata = make_json_safe(self._metadata_for_output(output_path))
                metadata["qgis_result"] = make_json_safe(result)
                parameters = {"output_path": output_path, "algorithm_id": "gdal:translate"}
            else:
                raise ToolValidationError("export_result supports vector and raster layers only.")
            exported = self.layer_registrar.register(
                name=Path(output_path).stem,
                kind=record.kind,
                source=str(Path(output_path).resolve()),
                role="final",
                parent_ids=[record.layer_id],
                algorithm_id="export_result",
                parameters=parameters,
                metadata=metadata,
            )
            return self.layer_registrar.success_observation(
                exported,
                message=f"Exported {record.name} to {output_path}.",
                data={"layer": exported.to_dict()},
            )
        except Exception as exc:
            return self._error_observation(exc)

    def _normalize_processing_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in dict(parameters or {}).items():
            if str(key) in PROCESSING_LAYER_REF_KEYS:
                normalized[key] = self._normalize_processing_value(value)
            else:
                normalized[key] = value
        return normalized

    def _collect_parent_ids(self, parameters: dict[str, Any]) -> list[str]:
        parent_ids: list[str] = []
        for value in self._iter_layer_ref_parameter_values(dict(parameters or {})):
            if self._looks_like_layer_ref(value):
                try:
                    parent_ids.append(self.state.resolve(str(value)).layer_id)
                except KeyError:
                    continue
        return list(dict.fromkeys(parent_ids))

    def _looks_like_layer_ref(self, value: Any) -> bool:
        return isinstance(value, str) and self.state.has_layer(value)

    def _normalize_processing_value(self, value: Any) -> Any:
        if self._looks_like_layer_ref(value):
            record = self.state.resolve(str(value))
            if record.kind == "table":
                return str(record.metadata.get("source_uri") or csv_uri_for_path(record.source, encoding=str(record.metadata.get("encoding") or "")))
            return record.source
        if isinstance(value, list):
            return [self._normalize_processing_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._normalize_processing_value(item) for item in value]
        return value

    def _iter_processing_values(self, values: Any):
        for value in values:
            if isinstance(value, (list, tuple)):
                yield from self._iter_processing_values(value)
            else:
                yield value

    def _iter_layer_ref_parameter_values(self, parameters: dict[str, Any]):
        for key, value in dict(parameters or {}).items():
            if str(key) not in PROCESSING_LAYER_REF_KEYS:
                continue
            if isinstance(value, (list, tuple)):
                yield from self._iter_processing_values(value)
            else:
                yield value

    def batch_reproject_layers(
        self,
        input_refs: list[str],
        *,
        target_crs: str,
        output_name: str = "",
    ) -> Observation:
        """Reproject multiple layers to the same target CRS."""
        self._begin_output_path_tracking()
        try:
            layers = []
            for ref in input_refs:
                record = self.state.resolve(str(ref).strip())
                if record.kind != "vector":
                    raise ToolValidationError(f"batch_reproject_layers requires vector layers; {ref} is {record.kind}.")
                layers.append(record)

            results = []
            for record in layers:
                output = self._next_temp_output_path(
                    "native:reprojectlayer",
                    output_name=f"{record.name}_reprojected",
                )
                result = self.runtime.run_algorithm(
                    "native:reprojectlayer",
                    {"INPUT": record.source, "TARGET_CRS": target_crs, "OUTPUT": output},
                )
                metadata = make_json_safe(result)
                exported = self.layer_registrar.register(
                    name=output_name or f"{record.name}_{target_crs.replace(':', '_')}",
                    kind="vector",
                    source=output,
                    role="intermediate",
                    parent_ids=[record.layer_id],
                    algorithm_id="batch_reproject_layers",
                    parameters={"input_refs": input_refs, "target_crs": target_crs},
                    metadata=metadata,
                )
                results.append({"layer_id": exported.layer_id, "name": exported.name, "source": exported.source})

            return Observation(
                status="success",
                message=f"Reprojected {len(results)} layer(s) to {target_crs}.",
                output_layer_id=results[0]["layer_id"] if results else "",
                output_path=results[0]["source"] if results else "",
                data=self._with_output_path_warnings({"layers": results, "count": len(results)}),
            )
        except Exception as exc:
            return self._error_observation(exc)

    def _record_artifact(self, record: LayerRecord, *, role: ArtifactRole) -> None:
        self.artifact_recorder.record(record, role=role)

    @staticmethod
    def _existing_path(input_path: str) -> str:
        return QGISDataSourceInspector.existing_path(input_path)

    @staticmethod
    def _inspect_csv(input_path: str) -> dict[str, Any]:
        return QGISDataSourceInspector.inspect_csv(input_path)

    @staticmethod
    def _read_text_with_fallback(input_path: str) -> tuple[str, str]:
        return QGISDataSourceInspector.read_text_with_fallback(input_path)

    @staticmethod
    def _normalize_export_path(output_path: str, *, default_stem: str) -> str:
        return QGISOutputResolver.normalize_export_path(output_path, default_stem=default_stem)

    @staticmethod
    def _normalize_raster_export_path(output_path: str, *, default_stem: str) -> str:
        return QGISOutputResolver.normalize_raster_export_path(output_path, default_stem=default_stem)

    @staticmethod
    def _csv_field_diagnostics(fields: list[str]) -> dict[str, Any]:
        return QGISDataSourceInspector.csv_field_diagnostics(fields)

    @staticmethod
    def _looks_like_mojibake(value: str) -> bool:
        return QGISDataSourceInspector.looks_like_mojibake(value)

    def _ensure_disk_backed_outputs(
        self,
        algorithm_id: str,
        parameters: dict[str, Any],
        *,
        output_name: str = "",
    ) -> dict[str, Any]:
        return self.processing_outputs.ensure_disk_backed_outputs(
            algorithm_id,
            parameters,
            output_name=output_name,
        )

    def _next_temp_output_path(self, algorithm_id: str, *, output_name: str = "", output_key: str = "OUTPUT") -> str:
        return self.output_resolver.next_temp_output_path(
            algorithm_id,
            output_name=output_name,
            output_key=output_key,
        )

    def _begin_output_path_tracking(self) -> None:
        self.output_resolver.begin_tracking()

    def _with_output_path_warnings(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.output_resolver.with_warnings(data)

    def _drain_output_path_warnings(self) -> list[dict[str, Any]]:
        return self.output_resolver.drain_warnings()

    @staticmethod
    def _available_output_path(path: Path) -> Path:
        return QGISOutputResolver.available_output_path(path)

    @staticmethod
    def _output_suffix_for_algorithm(algorithm_id: str) -> str:
        return QGISOutputResolver.output_suffix_for_algorithm(algorithm_id)

    @staticmethod
    def _needs_disk_output(value: Any) -> bool:
        return QGISOutputResolver.needs_disk_output(value)

    @staticmethod
    def _safe_name(value: str) -> str:
        return QGISOutputResolver.safe_name(value)

    @staticmethod
    def _extract_output_path(result: dict[str, Any], parameters: dict[str, Any] | None = None) -> str:
        return QGISProcessingOutputHandler.extract_output_path(result, parameters)

    def _metadata_for_output(self, output_path: str) -> dict[str, Any]:
        return self.metadata_normalizer.metadata_for_output(output_path)

    @staticmethod
    def _metadata_with_fallback_crs(metadata: dict[str, Any], crs: str) -> dict[str, Any]:
        return QGISMetadataNormalizer.metadata_with_fallback_crs(metadata, crs)

    @staticmethod
    def _kind_from_output(output_path: str) -> str:
        return QGISMetadataNormalizer.kind_from_output(output_path)

    @staticmethod
    def _derive_output_name(algorithm_id: str, output_path: str) -> str:
        return QGISMetadataNormalizer.derive_output_name(algorithm_id, output_path)

    @staticmethod
    def _error_observation(exc: Exception) -> Observation:
        if isinstance(exc, (QGISRuntimeError, ToolExecutionError, ToolValidationError)):
            data = {"error_code": exc.code, "error_data": exc.data}
            message = exc.message
        else:
            data = {"error_code": exc.__class__.__name__}
            message = str(exc)
        return Observation(status="error", message=message, data=data)


def _layer_summary(record: LayerRecord, *, detail_level: str = "summary") -> dict[str, Any]:
    metadata = dict(record.metadata or {})
    fields = _field_summaries(list(metadata.get("fields") or []), metadata=metadata)
    detail = str(detail_level or "summary").strip().lower()
    if detail not in {"summary", "fields", "full"}:
        detail = "summary"
    payload: dict[str, Any] = {
        "layer_id": record.layer_id,
        "name": record.name,
        "kind": record.kind,
        "source": record.source,
        "crs": str(metadata.get("crs") or ""),
        "geometry_type": str(metadata.get("geometry_type") or ""),
        "feature_count": metadata.get("feature_count", metadata.get("row_count")),
        "field_count": len(fields),
        "fields": fields,
        "extent": metadata.get("extent") or metadata.get("bounds"),
        "quality_flags": list(metadata.get("quality_flags") or metadata.get("warnings") or []),
        "lineage": {
            "algorithm_id": record.algorithm_id,
            "parent_ids": list(record.parent_ids),
            "parameters": make_json_safe(dict(record.parameters or {})),
        },
        "detail_level": detail,
    }
    if detail == "summary":
        payload["fields"] = fields[:20]
    if detail == "full":
        payload["metadata"] = make_json_safe(metadata)
    return make_json_safe(payload)


def _field_summaries(fields: list[Any], *, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    scoped_metadata = dict(metadata)
    scoped_metadata["fields"] = list(fields)
    return make_json_safe(field_records(scoped_metadata))


def _layer_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary.get('name') or summary.get('layer_id') or 'Layer'}",
        "",
        f"- Kind: {summary.get('kind') or 'unknown'}",
        f"- CRS: {summary.get('crs') or 'unknown'}",
        f"- Geometry: {summary.get('geometry_type') or 'none'}",
        f"- Features/rows: {summary.get('feature_count') if summary.get('feature_count') is not None else 'unknown'}",
        f"- Fields: {summary.get('field_count') if summary.get('field_count') is not None else 0}",
    ]
    extent = summary.get("extent")
    if extent:
        lines.append(f"- Extent: {extent}")
    source = str(summary.get("source") or "")
    if source:
        lines.append(f"- Source: {Path(source).name or source}")
    fields = [dict(item) for item in list(summary.get("fields") or []) if isinstance(item, dict)]
    if fields:
        lines.extend(["", "## Fields"])
        for field in fields:
            field_type = f" ({field.get('type')})" if field.get("type") else ""
            extras: list[str] = []
            if "null_count" in field:
                extras.append(f"nulls={field.get('null_count')}")
            if field.get("sample_values"):
                extras.append(f"samples={field.get('sample_values')}")
            suffix = f" - {', '.join(extras)}" if extras else ""
            lines.append(f"- {field.get('name')}{field_type}{suffix}")
    quality_flags = list(summary.get("quality_flags") or [])
    if quality_flags:
        lines.extend(["", "## Quality flags"])
        for flag in quality_flags:
            lines.append(f"- {flag}")
    return "\n".join(lines)
