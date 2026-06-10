"""Metadata and naming helpers for QGIS toolbox outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class QGISMetadataNormalizer:
    """Normalize output metadata without owning QGIS execution."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def metadata_for_output(self, output_path: str) -> dict[str, Any]:
        if not output_path:
            return {}
        if self.kind_from_output(output_path) == "raster":
            try:
                return dict(self.runtime.inspect_raster_path(output_path))
            except Exception:
                return {"source_path": output_path}
        try:
            return dict(self.runtime.inspect_vector_path(output_path))
        except Exception:
            return {"source_path": output_path}

    @staticmethod
    def metadata_with_fallback_crs(metadata: dict[str, Any], crs: str) -> dict[str, Any]:
        payload = dict(metadata or {})
        if not str(payload.get("crs") or "").strip() and str(crs or "").strip():
            payload["crs"] = str(crs or "").strip()
        return payload

    @staticmethod
    def kind_from_output(output_path: str) -> str:
        suffix = Path(str(output_path or "")).suffix.lower()
        if suffix in {".geojson", ".gpkg", ".shp"}:
            return "vector"
        if suffix in {".tif", ".tiff", ".img"}:
            return "raster"
        return "memory"

    @staticmethod
    def derive_output_name(algorithm_id: str, output_path: str) -> str:
        if output_path:
            return Path(output_path).stem or algorithm_id.replace(":", "_")
        return algorithm_id.replace(":", "_")
