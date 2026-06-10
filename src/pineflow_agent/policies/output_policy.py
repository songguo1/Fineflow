"""Output destination policy for GIS tools and result projection."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Literal

from pineflow_agent.core.json_safety import make_json_safe

ArtifactRoleName = Literal["input", "intermediate", "final", "report"]


RASTER_OUTPUT_ALGORITHMS = {
    "gdal:warpreproject",
    "gdal:cliprasterbymasklayer",
    "gdal:cliprasterbyextent",
    "qgis:rastercalculator",
    "gdal:rasterize",
    "gdal:translate",
    "gdal:slope",
    "gdal:aspect",
    "gdal:hillshade",
    "gdal:contour",
    "gdal:triterrainruggednessindex",
    "gdal:tpitopographicpositionindex",
    "gdal:roughness",
}


@dataclass(frozen=True)
class OutputOverwriteDecision:
    output_path: str
    exists: bool
    confirmation_required: bool
    params: dict[str, Any]


def needs_disk_output(value: Any) -> bool:
    """Return True when a QGIS output value must be replaced by a real file path."""
    if value is None:
        return True
    text = str(value or "").strip()
    if not text:
        return True
    upper = text.upper()
    if upper == "TEMPORARY_OUTPUT":
        return True
    if text.startswith("memory:") or text.startswith("<Qgs"):
        return True
    return False


def output_suffix_for_algorithm(algorithm_id: str) -> str:
    if str(algorithm_id or "").strip().lower() in RASTER_OUTPUT_ALGORITHMS:
        return ".tif"
    return ".gpkg"


def output_auto_renamed_warning(requested_path: Path, output_path: Path) -> dict[str, Any]:
    return make_json_safe(
        {
            "code": "output_auto_renamed",
            "category": "output_risk",
            "severity": "warning",
            "message": f"Auto-generated output path already existed; using {output_path.name} instead.",
            "technical_detail": f"Requested output path {requested_path} already existed. New output path: {output_path}.",
            "output_path": str(output_path),
            "requested_output_path": str(requested_path),
            "affects_result_trust": False,
        }
    )


def output_overwrite_decision(
    output_path: str,
    *,
    action: str = "",
    overwrite: bool = False,
) -> OutputOverwriteDecision:
    path = str(output_path or "").strip()
    if not path or needs_disk_output(path) or bool(overwrite):
        return OutputOverwriteDecision(
            output_path=path,
            exists=False,
            confirmation_required=False,
            params={"output_path": path, "action": action},
        )
    try:
        exists = Path(path).expanduser().exists()
    except OSError:
        exists = False
    return OutputOverwriteDecision(
        output_path=path,
        exists=exists,
        confirmation_required=exists,
        params={"output_path": path, "action": action},
    )


def is_input_layer(layer: dict[str, Any]) -> bool:
    return not str(layer.get("algorithm_id") or "").strip() and not list(layer.get("parent_ids") or [])


def should_expose_layer_output(layer: dict[str, Any]) -> bool:
    source = str(layer.get("source") or "")
    if not source:
        return False
    if needs_disk_output(source):
        return False
    if is_temp_session_output_path(source):
        return False
    if is_input_layer(layer):
        return False
    return True


def is_materialized_output(path: str) -> bool:
    return bool(path and not needs_disk_output(path))


def is_reusable_output(path: str, role: ArtifactRoleName) -> bool:
    if role in {"final", "report", "input"}:
        return True
    if not is_materialized_output(path):
        return False
    normalized = str(path).replace("/", os.sep).lower()
    return f"{os.sep}.pineflow{os.sep}sessions{os.sep}" in normalized or _path_exists(path)


def is_temp_session_output_path(path: str) -> bool:
    normalized = str(path or "").replace("/", "\\").lower()
    return "\\.pineflow\\sessions\\" in normalized and "\\temp\\" in normalized


def _path_exists(path: str) -> bool:
    if not path or needs_disk_output(path):
        return False
    try:
        return Path(path).exists()
    except (OSError, ValueError):
        return False
