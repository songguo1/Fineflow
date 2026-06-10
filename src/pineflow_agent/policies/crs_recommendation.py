"""CRS recommendation policy for distance-sensitive GIS operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import floor
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe

DEFAULT_PROJECTED_CRS = "EPSG:3857"


@dataclass(frozen=True)
class CRSRecommendation:
    target_crs: str
    confidence: str
    reason: str
    source: str = ""
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(
            {
                "target_crs": self.target_crs,
                "recommended_crs": self.target_crs,
                "confidence": self.confidence,
                "reason": self.reason,
                "source": self.source,
                "alternatives": list(self.alternatives),
                "requires_confirmation": self.requires_confirmation,
            }
        )


def recommend_projected_crs(layer: Any, *, task_type: str = "") -> CRSRecommendation:
    """Recommend a projected CRS for distance/area operations.

    v1 intentionally stays conservative: when a geographic extent is available,
    choose the local UTM zone; otherwise use Web Mercator with low confidence.
    """
    metadata = _metadata(layer)
    extent = _extent_tuple(metadata.get("extent"))
    if extent is None:
        return CRSRecommendation(
            target_crs=DEFAULT_PROJECTED_CRS,
            confidence="low",
            reason="Layer extent is unavailable; using Web Mercator as a generic projected CRS fallback.",
            source="fallback",
            alternatives=[],
            requires_confirmation=True,
        )

    lon = (extent[0] + extent[2]) / 2.0
    lat = (extent[1] + extent[3]) / 2.0
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return CRSRecommendation(
            target_crs=DEFAULT_PROJECTED_CRS,
            confidence="low",
            reason="Layer extent is not in longitude/latitude degrees; using generic projected CRS fallback.",
            source="fallback",
            alternatives=[],
            requires_confirmation=True,
        )

    zone = max(1, min(60, floor((lon + 180.0) / 6.0) + 1))
    epsg_prefix = 326 if lat >= 0 else 327
    target_crs = f"EPSG:{epsg_prefix}{zone:02d}"
    return CRSRecommendation(
        target_crs=target_crs,
        confidence="high",
        reason=f"Layer extent centroid is near lon {lon:.4f}, lat {lat:.4f}; UTM zone {zone} is suitable for local {task_type or 'distance'} analysis.",
        source="extent_utm_zone",
        alternatives=[
            {
                "target_crs": DEFAULT_PROJECTED_CRS,
                "reason": "Use Web Mercator only as a generic fallback when no better local projected CRS is available.",
                "source": "fallback",
            }
        ],
        requires_confirmation=True,
    )


def crs_recommendation_from_params(params: dict[str, Any]) -> dict[str, Any]:
    payload = dict(params or {})
    recommendation = payload.get("crs_recommendation")
    if isinstance(recommendation, dict) and recommendation:
        return normalize_crs_recommendation(recommendation)
    target_crs = str(payload.get("target_crs") or "").strip()
    if not target_crs:
        return {}
    return normalize_crs_recommendation(
        {
        "target_crs": target_crs,
        "recommended_crs": target_crs,
        "confidence": str(payload.get("crs_recommendation_confidence") or "medium"),
        "reason": str(payload.get("crs_recommendation_reason") or "Recommended CRS was supplied by validation context."),
        "source": str(payload.get("crs_recommendation_source") or "validation_context"),
        "alternatives": payload.get("crs_recommendation_alternatives") or [],
        "requires_confirmation": bool(payload.get("requires_confirmation", True)),
    }
    )


def normalize_crs_recommendation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    target_crs = str(value.get("target_crs") or value.get("recommended_crs") or "").strip()
    if not target_crs:
        return {}
    alternatives = []
    for item in list(value.get("alternatives") or []):
        if not isinstance(item, dict):
            continue
        alternative_target = str(item.get("target_crs") or item.get("recommended_crs") or "").strip()
        if not alternative_target or alternative_target == target_crs:
            continue
        alternatives.append(
            {
                "target_crs": alternative_target,
                "recommended_crs": alternative_target,
                "reason": str(item.get("reason") or "").strip(),
                "source": str(item.get("source") or "").strip(),
            }
        )
    return make_json_safe(
        {
            "target_crs": target_crs,
            "recommended_crs": target_crs,
            "confidence": str(value.get("confidence") or "medium"),
            "reason": str(value.get("reason") or "Recommended CRS was supplied by validation context."),
            "source": str(value.get("source") or "validation_context"),
            "alternatives": alternatives,
            "requires_confirmation": bool(value.get("requires_confirmation", True)),
        }
    )


def explicit_crs_recommendation(
    *,
    target_crs: str,
    reason: str,
    source: str,
    confidence: str = "high",
    alternatives: list[dict[str, Any]] | None = None,
    requires_confirmation: bool = True,
) -> CRSRecommendation:
    return CRSRecommendation(
        target_crs=str(target_crs or "").strip(),
        confidence=str(confidence or "high"),
        reason=str(reason or "").strip(),
        source=str(source or "").strip(),
        alternatives=[dict(item) for item in list(alternatives or []) if isinstance(item, dict)],
        requires_confirmation=bool(requires_confirmation),
    )


def _metadata(layer: Any) -> dict[str, Any]:
    if hasattr(layer, "metadata"):
        return dict(getattr(layer, "metadata") or {})
    if isinstance(layer, dict):
        return dict(layer.get("metadata") or {})
    return {}


def _extent_tuple(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, dict):
        xmin = _to_float(_first_present(value, ("xmin", "x_min", "minx")))
        ymin = _to_float(_first_present(value, ("ymin", "y_min", "miny")))
        xmax = _to_float(_first_present(value, ("xmax", "x_max", "maxx")))
        ymax = _to_float(_first_present(value, ("ymax", "y_max", "maxy")))
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        xmin = _to_float(value[0])
        ymin = _to_float(value[1])
        xmax = _to_float(value[2])
        ymax = _to_float(value[3])
    else:
        return None
    if None in (xmin, ymin, xmax, ymax):
        return None
    return (min(xmin, xmax), min(ymin, ymax), max(xmin, xmax), max(ymin, ymax))


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
