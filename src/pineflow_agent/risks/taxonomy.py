"""Risk taxonomy mapping for GIS validation and runtime warnings."""

from __future__ import annotations

CRS_CODES = {
    "distance_requires_projected_crs",
    "overlay_crs_mismatch",
    "unknown_crs",
    "raster_crs_mismatch",
    "output_crs_unknown",
}
FIELD_CODES = {"unknown_field", "missing_slot", "no_numeric_fields"}
LAYER_CODES = {"unknown_layer", "layer_kind_mismatch", "unknown_geometry_type"}
OUTPUT_CODES = {"output_exists", "output_file_missing", "output_auto_renamed"}
EMPTY_CODES = {"empty_feature_output", "empty_table_output", "contour_empty_output"}
GEOMETRY_CODES = {"invalid_geometry", "spatial_predicate_geometry_mismatch"}
RASTER_CODES = {
    "raster_slope_output",
    "raster_hillshade_output",
    "raster_extent_no_overlap",
    "raster_extent_partial_overlap",
    "raster_pixel_size_mismatch",
    "raster_nodata_propagation",
    "raster_resampling_recommendation",
}
DATA_QUALITY_CODES = {"csv_encoding_issue", "feature_count_check_note"}


def category_for_code(code: str, stage: str = "") -> str:
    normalized = str(code or "").strip()
    if normalized in CRS_CODES:
        return "crs_risk"
    if normalized in FIELD_CODES:
        return "field_risk"
    if normalized in LAYER_CODES:
        return "layer_ambiguity"
    if normalized in OUTPUT_CODES:
        return "output_risk"
    if normalized in EMPTY_CODES:
        return "empty_result_risk"
    if normalized in GEOMETRY_CODES:
        return "geometry_risk"
    if normalized in RASTER_CODES:
        return "raster_risk"
    if normalized in DATA_QUALITY_CODES:
        return "data_quality_risk"
    return "data_quality_risk"
