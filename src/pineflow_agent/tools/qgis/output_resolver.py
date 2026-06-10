"""Output path resolution helpers for QGIS toolbox operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pineflow_runtime.errors import ToolValidationError

from pineflow_agent.core.workspace import WorkspaceContext, safe_workspace_name
from pineflow_agent.policies.output_policy import (
    needs_disk_output,
    output_auto_renamed_warning,
    output_suffix_for_algorithm,
)


class QGISOutputResolver:
    """Resolve materialized output paths and collect path warnings."""

    def __init__(self, workspace: WorkspaceContext) -> None:
        self.workspace = workspace
        self._temp_index = 0
        self._output_path_warnings: list[dict[str, Any]] = []

    def set_workspace(self, workspace: WorkspaceContext) -> None:
        self.workspace = workspace

    def next_temp_output_path(self, algorithm_id: str, *, output_name: str = "", output_key: str = "OUTPUT") -> str:
        self._temp_index += 1
        base_name = output_name or algorithm_id.replace(":", "_")
        if output_key not in {"OUTPUT", "OUTPUT_LAYER"}:
            base_name = f"{base_name}_{output_key.lower()}"
        suffix = output_suffix_for_algorithm(algorithm_id)
        file_name = f"{self._temp_index:02d}_{safe_workspace_name(base_name)}{suffix}"
        requested_path = Path(self.workspace.temp_output_path(file_name))
        output_path = self.available_output_path(requested_path)
        if output_path != requested_path:
            self._output_path_warnings.append(output_auto_renamed_warning(requested_path, output_path))
        return str(output_path)

    def begin_tracking(self) -> None:
        self._output_path_warnings = []

    def with_warnings(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(data or {})
        warnings = self.drain_warnings()
        if warnings:
            payload["postflight_warnings"] = [*list(payload.get("postflight_warnings") or []), *warnings]
        return payload

    def drain_warnings(self) -> list[dict[str, Any]]:
        warnings = list(self._output_path_warnings or [])
        self._output_path_warnings = []
        return warnings

    @staticmethod
    def normalize_export_path(output_path: str, *, default_stem: str) -> str:
        raw = Path(str(output_path or "").strip()).expanduser()
        if not str(raw):
            raise ToolValidationError("export_result requires an output path.")
        if raw.exists() and raw.is_dir():
            raw = raw / f"{safe_workspace_name(default_stem or 'export')}.shp"
        elif not raw.suffix:
            raw = raw.with_suffix(".shp")
        return str(raw.resolve())

    @staticmethod
    def normalize_raster_export_path(output_path: str, *, default_stem: str) -> str:
        raw = Path(str(output_path or "").strip()).expanduser()
        if not str(raw):
            raise ToolValidationError("export_result requires an output path.")
        if raw.exists() and raw.is_dir():
            raw = raw / f"{safe_workspace_name(default_stem or 'export')}.tif"
        elif not raw.suffix:
            raw = raw.with_suffix(".tif")
        if raw.suffix.lower() not in {".tif", ".tiff"}:
            raise ToolValidationError("Raster export supports .tif and .tiff outputs.")
        return str(raw.resolve())

    @staticmethod
    def available_output_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        for index in range(2, 1000):
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
        raise ToolValidationError(f"Could not allocate a unique output path near {path}.")

    @staticmethod
    def needs_disk_output(value: Any) -> bool:
        return needs_disk_output(value)

    @staticmethod
    def output_suffix_for_algorithm(algorithm_id: str) -> str:
        return output_suffix_for_algorithm(algorithm_id)

    @staticmethod
    def safe_name(value: str) -> str:
        return safe_workspace_name(value)
