"""Small access helpers for optional toolbox capabilities."""

from __future__ import annotations

from typing import Any


def toolbox_artifacts(toolbox: Any) -> list[dict[str, Any]]:
    artifact_index = toolbox_artifact_index(toolbox)
    if artifact_index is None or not hasattr(artifact_index, "outputs"):
        return []
    try:
        return [dict(item) for item in list(artifact_index.outputs(include_inputs=True) or []) if isinstance(item, dict)]
    except Exception:
        return []


def toolbox_artifact_index(toolbox: Any) -> Any:
    return getattr(toolbox, "artifacts", None)
