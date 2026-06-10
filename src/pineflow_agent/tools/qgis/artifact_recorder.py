"""Artifact recording helper for QGIS toolbox operations."""

from __future__ import annotations

from pineflow_agent.core.artifacts import ArtifactIndex, ArtifactRecord, ArtifactRole
from pineflow_agent.core.state_tree import LayerRecord
from pineflow_agent.core.workspace import WorkspaceContext


class QGISArtifactRecorder:
    """Record toolbox layer outputs without making tool success depend on indexing."""

    def __init__(self, workspace: WorkspaceContext) -> None:
        self.workspace = workspace
        self.artifacts = ArtifactIndex.for_workspace(workspace)

    def set_workspace(self, workspace: WorkspaceContext) -> None:
        self.workspace = workspace
        self.artifacts = ArtifactIndex.for_workspace(workspace)

    def record(
        self,
        record: LayerRecord,
        *,
        role: ArtifactRole,
        source_step: int | None = None,
        source_run_id: str = "",
        source_action: str = "",
    ) -> ArtifactRecord | None:
        try:
            if not record.source or record.source == "TEMPORARY_OUTPUT" or str(record.source).startswith("memory:"):
                return None
            return self.artifacts.register_layer(
                record.to_dict(),
                role=role,
                source_step=source_step,
                source_run_id=source_run_id,
                source_action=source_action,
            )
        except Exception:
            # Artifact indexing must never make a successful GIS tool fail.
            return None
