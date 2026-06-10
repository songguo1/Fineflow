"""Processing output parameter helpers for QGIS toolbox operations."""

from __future__ import annotations

from typing import Any

from pineflow_agent.tools.qgis.output_resolver import QGISOutputResolver

PROCESSING_OUTPUT_KEYS = ("OUTPUT", "OUTPUT_LAYER", "OUTPUT_FILE", "VALID_OUTPUT", "INVALID_OUTPUT", "ERROR_OUTPUT")


class QGISProcessingOutputHandler:
    """Materialize QGIS processing outputs and recover output paths."""

    def __init__(self, output_resolver: QGISOutputResolver) -> None:
        self.output_resolver = output_resolver

    def ensure_disk_backed_outputs(
        self,
        algorithm_id: str,
        parameters: dict[str, Any],
        *,
        output_name: str = "",
    ) -> dict[str, Any]:
        normalized = dict(parameters or {})
        output_keys = [key for key in PROCESSING_OUTPUT_KEYS if key in normalized]
        if not output_keys:
            output_keys = ["OUTPUT"]
            normalized["OUTPUT"] = ""

        for key in output_keys:
            if self.output_resolver.needs_disk_output(normalized.get(key)):
                normalized[key] = self.output_resolver.next_temp_output_path(
                    algorithm_id,
                    output_name=output_name,
                    output_key=key,
                )
        return normalized

    @staticmethod
    def extract_output_path(result: dict[str, Any], parameters: dict[str, Any] | None = None) -> str:
        for key in PROCESSING_OUTPUT_KEYS:
            value = result.get(key)
            if value and not QGISOutputResolver.needs_disk_output(value):
                return str(value)
            fallback = (parameters or {}).get(key)
            if fallback and not QGISOutputResolver.needs_disk_output(fallback):
                return str(fallback)
        return ""
