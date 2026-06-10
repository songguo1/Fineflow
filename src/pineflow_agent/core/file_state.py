"""Serializable file-state view for a PineFlow workspace session."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.artifacts import ArtifactIndex
from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext


def workspace_file_state(
    workspace: WorkspaceContext,
    *,
    artifacts: ArtifactIndex | None = None,
    event_count: int = 0,
    updated_at: str = "",
) -> dict[str, Any]:
    """Return the public file-state index for one session workspace."""

    artifact_index = artifacts or ArtifactIndex.for_workspace(workspace)
    return make_json_safe(
        {
            "version": 2,
            "pineflow_dir": str(workspace.pineflow_dir),
            "sessions_root_dir": str(workspace.sessions_root_dir),
            "manifest_path": str(workspace.manifest_path),
            "event_log_path": str(workspace.event_log_path),
            "steps_path": str(workspace.steps_path),
            "state_tree_path": str(workspace.state_tree_path),
            "pending_path": str(workspace.pending_path),
            "artifact_index_path": str(artifact_index.path),
            "layers_dir": str(workspace.layers_dir),
            "session_memory_path": str(workspace.session_memory_path),
            "outputs_dir": str(workspace.outputs_dir),
            "temp_dir": str(workspace.temp_dir),
            "artifacts": artifact_index.to_dict().get("artifacts", []),
            "event_count": int(event_count or 0),
            "updated_at": str(updated_at or ""),
        }
    )
