"""Helpers for keeping ReAct state JSON serializable."""

from __future__ import annotations

from pathlib import Path
from typing import Any


JSON_SCALAR_TYPES = (str, int, float, bool, type(None))


def make_json_safe(value: Any) -> Any:
    """Convert QGIS/Python objects into JSON-safe values for prompts and logs."""
    if isinstance(value, JSON_SCALAR_TYPES):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "source") and callable(value.source):
        try:
            return str(value.source())
        except Exception:
            pass
    if hasattr(value, "id") and callable(value.id):
        try:
            return str(value.id())
        except Exception:
            pass
    return str(value)
