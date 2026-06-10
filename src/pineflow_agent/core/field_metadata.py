"""Small helpers for normalizing layer field metadata."""

from __future__ import annotations

from typing import Any


def field_names(metadata: dict[str, Any]) -> list[str]:
    return [record["name"] for record in field_records(metadata)]


def field_records(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    null_counts = metadata.get("null_counts") if isinstance(metadata.get("null_counts"), dict) else {}
    sample_values = metadata.get("sample_values") if isinstance(metadata.get("sample_values"), dict) else {}
    field_types = metadata.get("field_types") if isinstance(metadata.get("field_types"), dict) else {}
    details = _details_by_name(metadata.get("field_summaries"))

    records: list[dict[str, Any]] = []
    source_fields = list(metadata.get("fields") or [])
    if not source_fields:
        source_fields = list(metadata.get("field_summaries") or [])
    for field in source_fields:
        if isinstance(field, dict):
            name = str(field.get("name") or field.get("field") or "").strip()
            record = dict(field)
        else:
            name = str(field or "").strip()
            record = {}
        if not name:
            continue

        detail = dict(details.get(name) or {})
        detail.update(record)
        item: dict[str, Any] = {"name": name}
        field_type = str(detail.get("type") or detail.get("field_type") or field_types.get(name) or "").strip()
        if field_type:
            item["type"] = field_type
        if name in null_counts:
            item["null_count"] = null_counts.get(name)
        elif "null_count" in detail:
            item["null_count"] = detail.get("null_count")
        samples = sample_values.get(name) if name in sample_values else detail.get("sample_values")
        if samples:
            item["sample_values"] = list(samples or [])
        records.append({key: value for key, value in item.items() if value not in ("", None)})
    return records


def _details_by_name(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in list(value or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("field") or "").strip()
        if name:
            result[name] = dict(item)
    return result
